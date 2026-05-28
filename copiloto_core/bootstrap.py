"""Bootstrap del schema platform del core en una DB consumer.

# Por qué existe este módulo (v1.2.0)

Cuando un consumer hace `pip install copiloto-core`, recibe la
**librería Python** del core — pero NO la infraestructura
operacional. En particular, el schema `app.*` (tenants, users,
rbac, audit, sessions, rate-limit buckets, ai providers…) vive
en archivos SQL bajo `copiloto_core/platform_schema/`. Sin
aplicarlos a una DB vacía, cualquier endpoint del core o de un
módulo opt-in falla apenas intenta tocar `app.tenants` o
`current_setting('app.tenant_id')`.

Antes de v1.2.0 esto se hacía con `scripts/bootstrap.sh` del repo
del core, que ejecuta `psql -f infra/postgres/10-core.sql`. Eso
no es accesible al consumer.

Este módulo expone `apply_platform_schema(conn)` que:
  1. Aplica los SQL del schema platform en orden, idempotentemente.
  2. Trackea lo aplicado en `app.schema_migrations` con SHA-256
     (mismo patrón que el runner de migrations de módulos).
  3. Opcionalmente crea el rol `copiloto_app` con la password de
     `APP_DB_PASSWORD` para que el runtime de la app pueda
     conectarse con permisos limitados (RLS-friendly).

Lo invocás vía CLI:

    python -m copiloto_core bootstrap

O desde código (e.g. en un test setUp o en un script propio):

    from copiloto_core import apply_platform_schema
    async with admin_conn() as conn:
        applied = await apply_platform_schema(conn)
"""
from __future__ import annotations

import hashlib
import logging
import re
from importlib import resources
from typing import TYPE_CHECKING

from copiloto_core.migrations.runner import ensure_schema_migrations_table

if TYPE_CHECKING:
    import asyncpg


logger = logging.getLogger(__name__)


# Identidad del platform schema en `app.schema_migrations`. Reservado.
# Un módulo opt-in NO puede usar este code (`CoreModule.code = 'core'`
# rompería el regex, así que está naturalmente protegido).
_PLATFORM_MODULE_CODE = 'core'

# Orden estricto de aplicación. `10-core.sql` define el schema; debe
# correrse antes que `20-seed.sql` (que inserta el tenant demo).
_PLATFORM_SQL_FILES: tuple[str, ...] = ('10-core.sql', '20-seed.sql')

# Identificador del rol app: snake_case válido, evita SQL injection
# cuando se interpola en `CREATE ROLE`.
_APP_USER_RE = re.compile(r'^[a-z][a-z0-9_]{0,30}$')


class BootstrapError(Exception):
    """Fallo al aplicar el platform schema."""


def _read_platform_sql(filename: str) -> str:
    """Lee un SQL del platform schema via `importlib.resources`.

    Funciona tanto cuando el core está instalado como wheel (pip),
    editable (-e), o desde source. Evita asumir layout filesystem.
    """
    try:
        ref = resources.files('copiloto_core.platform_schema').joinpath(filename)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise BootstrapError(
            f'No se pudo localizar copiloto_core.platform_schema/{filename}: {exc}',
        ) from exc
    if not ref.is_file():
        raise BootstrapError(
            f'Platform schema SQL no encontrado: {filename}. '
            f'Verificá que el package copiloto-core esté instalado '
            f'completamente (los .sql viajan como package-data).',
        )
    return ref.read_text(encoding='utf-8')


async def _platform_versions_applied(
    conn: 'asyncpg.Connection',
) -> set[str]:
    """Versions ya aplicadas del platform schema. {} si la tabla no existe."""
    table_exists = await conn.fetchval("select to_regclass('app.schema_migrations')")
    if not table_exists:
        return set()
    rows = await conn.fetch(
        'select version from app.schema_migrations where module = $1',
        _PLATFORM_MODULE_CODE,
    )
    return {r['version'] for r in rows}


async def _create_app_role(
    conn: 'asyncpg.Connection',
    app_user: str,
    app_password: str,
) -> bool:
    """Crea el rol `app_user` con LOGIN + password (SIN grants).

    Solo creación del rol — los grants vienen aparte porque dependen
    del schema `app` que aún no existe en este punto del bootstrap.

    Idempotente: si el rol ya existe, no-op.

    Returns:
      True si creó el rol, False si ya existía.

    Raises:
      BootstrapError: si `app_user` no matchea el regex de seguridad.
    """
    if not _APP_USER_RE.match(app_user):
        raise BootstrapError(
            f'app_user inválido: {app_user!r}. Debe matchear '
            f'{_APP_USER_RE.pattern!r} (snake_case, 1-31 chars).',
        )

    exists = await conn.fetchval(
        'select 1 from pg_roles where rolname = $1',
        app_user,
    )
    if exists:
        logger.info('bootstrap.app_user_exists user=%s', app_user)
        return False

    # app_user ya validado por regex → safe interpolation.
    # app_password se escapa como literal SQL (' → '').
    pw_escaped = app_password.replace("'", "''")
    await conn.execute(
        f"create role {app_user} with login password '{pw_escaped}'",
    )
    logger.info('bootstrap.app_user_created user=%s', app_user)
    return True


async def _grant_app_role_permissions(
    conn: 'asyncpg.Connection',
    app_user: str,
) -> None:
    """Aplica los GRANTs del rol app sobre el schema `app`.

    Requiere que el schema `app` ya exista (lo crea 10-core.sql).
    Idempotente — re-aplicar es no-op.

    Permisos minimales para runtime de la app:
      - CONNECT a la DB actual.
      - USAGE en schema `app` + DML en todas las tablas.
      - USAGE+SELECT en sequences (para defaults `gen_random_uuid()`).
      - EXECUTE en functions (security definer las usa).

    RLS sigue aplicando — estos grants no bypassean policies.
    """
    grants = f"""
    grant connect on database current_database() to {app_user};
    grant usage on schema app to {app_user};
    grant select, insert, update, delete on all tables in schema app to {app_user};
    grant usage, select on all sequences in schema app to {app_user};
    grant execute on all functions in schema app to {app_user};
    alter default privileges in schema app
      grant select, insert, update, delete on tables to {app_user};
    alter default privileges in schema app
      grant usage, select on sequences to {app_user};
    alter default privileges in schema app
      grant execute on functions to {app_user};
    """
    await conn.execute(grants)


# Backward compat — el nombre viejo combina ambos pasos. Útil para
# tests/callers que quieran el shortcut clásico cuando el schema ya
# existe (e.g. re-bootstrap después de drop role).
async def _ensure_app_user(
    conn: 'asyncpg.Connection',
    app_user: str,
    app_password: str,
) -> bool:
    """Compat: crea rol + aplica grants. Usalo solo si el schema `app`
    ya existe. En el bootstrap del platform schema usá los dos pasos
    separados (`_create_app_role` antes de los SQLs, `_grant_app_role_permissions`
    después)."""
    created = await _create_app_role(conn, app_user, app_password)
    await _grant_app_role_permissions(conn, app_user)
    return created


async def apply_platform_schema(
    conn: 'asyncpg.Connection',
    *,
    seed: bool = True,
    create_app_user: bool = False,
    app_user: str | None = None,
    app_password: str | None = None,
) -> list[str]:
    """Aplica el schema platform del core a la DB conectada.

    `conn` debe tener permisos suficientes para CREATE EXTENSION,
    CREATE SCHEMA y (si `create_app_user=True`) CREATE ROLE. En
    práctica: usá la URL admin de postgres (`DATABASE_ADMIN_URL`).

    Args:
      conn: conexión asyncpg ya abierta.
      seed: si True (default), aplica también `20-seed.sql` que
        inserta el tenant demo. El seed requiere que el nombre de la
        DB contenga `dev|test|local` o que `app.allow_seed='true'`
        esté seteada en sesión (esta función la setea automáticamente
        ANTES del seed, para no abortar el bootstrap en DBs prod-named).
      create_app_user: si True, crea el rol limitado de runtime
        (`app_user` con `app_password`). Default False — opt-in.
      app_user: nombre del rol a crear. Debe matchear snake_case.
      app_password: password del rol. Sin restricciones de longitud.

    Returns:
      Lista de archivos SQL aplicados en este call. Vacía si todo
      estaba ya aplicado (idempotente).

    Raises:
      BootstrapError: si `create_app_user=True` sin `app_user`/`app_password`,
        o si `app_user` no matchea el regex, o si un SQL falla.
    """
    if create_app_user and (not app_user or not app_password):
        raise BootstrapError(
            'create_app_user=True requiere app_user y app_password.',
        )

    # v1.3.3: crear el rol app ANTES de aplicar los SQLs. `10-core.sql`
    # tiene `GRANT ... TO copiloto_app` hard-coded; si el rol no existe
    # al momento del GRANT, postgres aborta con `UndefinedObjectError:
    # role "copiloto_app" does not exist`.
    #
    # Pero los GRANTs del role sobre `app.*` van DESPUÉS de los SQLs
    # (porque el schema `app` no existe todavía). Dos pasos separados:
    #   1. _create_app_role        — solo CREATE ROLE
    #   2. (aplicar SQLs que crean el schema + tablas)
    #   3. _grant_app_role_permissions — GRANTs sobre schema `app`
    if create_app_user:
        assert app_user and app_password  # validado arriba
        await _create_app_role(conn, app_user, app_password)

    already_applied = await _platform_versions_applied(conn)

    sql_files: list[str] = ['10-core.sql']
    if seed:
        sql_files.append('20-seed.sql')

    applied: list[str] = []
    for sql_file in sql_files:
        version = sql_file[:-4]  # quitar `.sql`
        if version in already_applied:
            logger.info(
                'bootstrap.platform_already_applied version=%s', version,
            )
            continue

        sql_text = _read_platform_sql(sql_file)
        checksum = hashlib.sha256(sql_text.encode('utf-8')).hexdigest()

        # El seed tiene un guard que aborta si el DB name no contiene
        # dev|test|local. En contexto de pip install + DB de prod del
        # consumer, ese guard puede gatillar — el override evita el
        # raise. Es seguro porque el seed solo inserta el tenant demo
        # bajo `on conflict do nothing` (idempotente).
        if sql_file == '20-seed.sql':
            await conn.execute("set local app.allow_seed = 'true'")

        try:
            await conn.execute(sql_text)
        except Exception as exc:  # noqa: BLE001
            raise BootstrapError(
                f'Fallo al aplicar platform/{version}: '
                f'{type(exc).__name__}: {exc}',
            ) from exc

        # Tras 10-core.sql, app.schema_migrations existe (la crea
        # ensure_schema_migrations_table en run_module). Llamamos
        # ensure_* explícito para garantizar que existe incluso si
        # un futuro 10-core.sql no la incluyera.
        await ensure_schema_migrations_table(conn)

        await conn.execute(
            'insert into app.schema_migrations (module, version, sha256) '
            'values ($1, $2, $3) on conflict (module, version) do nothing',
            _PLATFORM_MODULE_CODE, version, checksum,
        )
        logger.info(
            'bootstrap.platform_applied version=%s sha256=%s...',
            version, checksum[:12],
        )
        applied.append(sql_file)

    # Aplicar GRANTs del rol app sobre schema `app` (ahora que existe).
    # En idempotent re-runs, los `grant ... to copiloto_app` que ya
    # están en 10-core.sql también corren acá — no hay daño porque
    # GRANT es idempotente, pero esto cubre el caso de un app_user
    # custom (`--app-user=mi_app`) que NO está mencionado en 10-core.sql.
    if create_app_user:
        await _grant_app_role_permissions(conn, app_user)

    return applied


__all__ = [
    'BootstrapError',
    'apply_platform_schema',
]
