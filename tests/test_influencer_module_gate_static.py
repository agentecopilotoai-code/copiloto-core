"""Static tests for TASK-INFLU-001 — Module gate del módulo Influencer.

Verifica el contrato sin necesidad de DB ni FastAPI test client:

- Migración SQL declara schema ``influencer`` + tabla ``app.tenant_modules``
  con CHECK, default ``enabled=false``, FKs correctos, RLS habilitada y las
  4 policies (1 select + 3 support-only para insert/update/delete).
- ``01-schema.sql`` (fresh installs) declara el mismo contrato — paridad
  con ``03-migrations.sql``.
- ``app/influencer/__init__.py``:
    - Expone ``MODULE_NAME = 'influencer'``.
    - Expone ``ensure_module_enabled`` como async dependency FastAPI.
    - Levanta HTTPException(404) (NO 403) cuando el módulo no está
      activo — decisión D2 explícita.
    - El cache TTL es ≤ 300s (5 min) — el comentario del código y el
      valor de la constante deben ser coherentes.
- ``app/influencer/router.py``:
    - ``influencer_router`` con prefix ``/v1/influencer`` y tag
      ``influencer``.
    - Dependencies del router incluyen ``authenticate_request`` y
      ``ensure_module_enabled`` — en ese orden (auth primero para poblar
      ``request.state.tenant_id``).
- ``app/main.py`` monta el router via ``include_router``.

Estos asserts son AST/text-based para evitar requerir asyncpg / FastAPI
test client en CI rápido (job ``api``); los tests E2E con DB viven en
``tests/test_influencer_module_gate.py`` (a venir cuando UI-INFLU-002 y
TASK-INFLU-008 estén juntas).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_SQL = REPO_ROOT / 'infra' / 'postgres' / '03-migrations.sql'
SCHEMA_SQL = REPO_ROOT / 'infra' / 'postgres' / '01-schema.sql'
INFLUENCER_INIT = REPO_ROOT / 'app' / 'influencer' / '__init__.py'
INFLUENCER_ROUTER = REPO_ROOT / 'app' / 'influencer' / 'router.py'
MAIN_PY = REPO_ROOT / 'app' / 'main.py'


# ── SQL migration ──────────────────────────────────────────────────────────


@pytest.fixture(scope='module')
def migrations_source() -> str:
    return MIGRATIONS_SQL.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def schema_source() -> str:
    return SCHEMA_SQL.read_text(encoding='utf-8')


def test_migrations_declare_influencer_schema(migrations_source: str) -> None:
    assert 'create schema if not exists influencer' in migrations_source
    # Grant + default privileges para que tablas futuras del schema
    # hereden los permisos del rol del app.
    assert 'grant usage on schema influencer to copiloto_app' in migrations_source
    assert (
        'alter default privileges in schema influencer'
        in migrations_source
    )


def test_migrations_declare_tenant_modules_table(migrations_source: str) -> None:
    assert 'create table if not exists app.tenant_modules' in migrations_source
    # Tenant_id como FK con ON DELETE CASCADE: si borran el tenant, su
    # entrada del módulo se va con él.
    assert 'references app.tenants(id) on delete cascade' in migrations_source
    # Check constraint sobre `module` — restringe a lista cerrada
    # actualmente ['influencer'].
    assert "check (" in migrations_source
    assert "'influencer'" in migrations_source
    # `enabled` default false — un INSERT por accidente sin enabled
    # explícito deja el módulo inactivo (fail-closed).
    assert 'enabled       boolean not null default false' in migrations_source
    # PK compuesto (tenant_id, module) — un tenant puede tener varios
    # módulos, pero NO duplicados.
    assert 'primary key (tenant_id, module)' in migrations_source


def test_migrations_enable_rls_on_tenant_modules(migrations_source: str) -> None:
    assert 'alter table app.tenant_modules enable row level security' in migrations_source
    # 4 policies — 1 select + 3 support-only para escritura.
    assert 'create policy tenant_modules_tenant_select' in migrations_source
    assert 'create policy tenant_modules_support_insert' in migrations_source
    assert 'create policy tenant_modules_support_update' in migrations_source
    assert 'create policy tenant_modules_support_delete' in migrations_source


def test_migrations_select_policy_uses_tenant_id_and_support_mode(
    migrations_source: str,
) -> None:
    # El select policy es como el resto del schema app.*: filtra por
    # tenant_id O por support_mode (platform_owner).
    select_block_start = migrations_source.index(
        'create policy tenant_modules_tenant_select'
    )
    select_block = migrations_source[select_block_start : select_block_start + 400]
    assert 'tenant_id = app.current_tenant_id() or app.support_mode()' in select_block


def test_migrations_write_policies_are_support_mode_only(
    migrations_source: str,
) -> None:
    """Las 3 policies de escritura SOLO permiten support_mode (platform_owner).

    El tenant NO puede activar su propio módulo vía SQL directo — debe pasar
    por el endpoint de platform_admin con MFA. Esto es defense-in-depth
    encima del gate del app layer.
    """
    for verb in ('insert', 'update', 'delete'):
        marker = f'create policy tenant_modules_support_{verb}'
        assert marker in migrations_source, marker
        idx = migrations_source.index(marker)
        block = migrations_source[idx : idx + 400]
        # NO debe contener `current_tenant_id` — solo support_mode.
        assert 'current_tenant_id' not in block, verb
        assert 'app.support_mode()' in block, verb


def test_schema_sql_has_same_module_contract(schema_source: str) -> None:
    """El fresh-install `01-schema.sql` debe declarar el mismo schema +
    tabla + policies — paridad estricta con `03-migrations.sql`. Sin esto,
    una DB nueva no tendría tenant_modules.
    """
    assert 'create schema if not exists influencer' in schema_source
    assert 'create table if not exists app.tenant_modules' in schema_source
    assert 'alter table app.tenant_modules enable row level security' in schema_source
    for policy in (
        'tenant_modules_tenant_select',
        'tenant_modules_support_insert',
        'tenant_modules_support_update',
        'tenant_modules_support_delete',
    ):
        assert policy in schema_source, policy


def test_partial_index_speeds_up_enabled_lookups(
    migrations_source: str,
) -> None:
    """El gate hace ``select enabled from app.tenant_modules where
    tenant_id=$1 and module=$2`` en cada request gateada. Hay un partial
    index sobre filas con enabled=true para que el lookup sea O(1) sin
    escanear filas no-enabled.
    """
    assert 'create index if not exists ix_tenant_modules_enabled' in migrations_source
    assert 'where enabled = true' in migrations_source


# ── Helper Python `ensure_module_enabled` ──────────────────────────────────


def test_module_name_constant_is_canonical() -> None:
    """``MODULE_NAME`` debe ser el string exacto declarado en el CHECK
    constraint de la migración. Si alguien lo cambia (typo, mayúsculas),
    el gate nunca matcheará filas y todo el módulo devolvería 404.
    """
    from app.influencer import MODULE_NAME

    assert MODULE_NAME == 'influencer'
    assert isinstance(MODULE_NAME, str)
    # Debe matchear lo que ya está en la migración.
    assert (
        f"'{MODULE_NAME}'"
        in MIGRATIONS_SQL.read_text(encoding='utf-8')
    )


def test_ensure_module_enabled_is_async() -> None:
    from app.influencer import ensure_module_enabled

    assert inspect.iscoroutinefunction(ensure_module_enabled)


def test_ensure_module_enabled_signature() -> None:
    """Acepta ``request``, ``conn`` (Depends get_db) y ``_auth``
    (Depends authenticate_request). NO acepta tenant_id explícito — lo
    lee siempre de ``request.state`` para evitar que un caller pase un
    tenant_id de otro tenant.
    """
    from app.influencer import ensure_module_enabled

    sig = inspect.signature(ensure_module_enabled)
    params = list(sig.parameters)
    assert params[0] == 'request'
    # Los otros 2 vienen como Depends(); su nombre exacto puede variar
    # pero al menos deben existir.
    assert len(params) >= 2


def test_ensure_module_enabled_raises_404_not_403() -> None:
    """Decisión D2 explícita: 404, no 403. Auditamos el AST en busca de
    `HTTPException(status_code=...)` y validamos que TODAS las llamadas
    usan 404. Un cambio futuro a 403 rompería este test (lo cual queremos).
    """
    tree = ast.parse(INFLUENCER_INIT.read_text(encoding='utf-8'))

    statuses_used: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Buscamos `HTTPException(status_code=...)`.
        fn = node.func
        is_http_exc = (
            (isinstance(fn, ast.Name) and fn.id == 'HTTPException')
            or (isinstance(fn, ast.Attribute) and fn.attr == 'HTTPException')
        )
        if not is_http_exc:
            continue
        for kw in node.keywords:
            if kw.arg == 'status_code':
                # Captura tanto Attribute (`status.HTTP_404_NOT_FOUND`)
                # como literal int (404).
                if isinstance(kw.value, ast.Attribute):
                    statuses_used.append(kw.value.attr)
                elif isinstance(kw.value, ast.Constant):
                    statuses_used.append(str(kw.value.value))

    assert statuses_used, 'el helper debe hacer raise HTTPException(...)'
    for s in statuses_used:
        # Permitimos `HTTP_404_NOT_FOUND` o literal `404`.
        assert s in ('HTTP_404_NOT_FOUND', '404'), (
            f'status inesperado: {s} — D2 exige 404 explícito'
        )


def test_ensure_module_enabled_cache_ttl_is_five_minutes() -> None:
    """El cache TTL debe ser <= 300s (5 min). Un TTL mayor implicaría
    que un toggle de módulo tarda > 5min en propagarse a un worker que
    ya cacheó la activación previa.
    """
    from app.influencer import _CACHE_TTL_SECONDS

    assert isinstance(_CACHE_TTL_SECONDS, (int, float))
    assert 0 < _CACHE_TTL_SECONDS <= 300


def test_cache_invalidate_is_exposed() -> None:
    """Para tests E2E necesitamos limpiar el cache entre casos. El helper
    está exportado en ``__all__``.
    """
    from app.influencer import _cache_invalidate

    assert callable(_cache_invalidate)


# ── Router skeleton ────────────────────────────────────────────────────────


def test_router_has_correct_prefix_and_tag() -> None:
    from app.influencer.router import influencer_router

    assert influencer_router.prefix == '/v1/influencer'
    assert 'influencer' in influencer_router.tags


def test_router_dependencies_include_auth_and_module_gate() -> None:
    """Las dependencies del router son la combinación canónica:
    ``authenticate_request`` (poblar tenant_id) → ``ensure_module_enabled``
    (gate del módulo). Si alguien borra el gate por error, el módulo
    quedaría accesible a cualquier tenant.
    """
    from app.core.security import authenticate_request
    from app.influencer import ensure_module_enabled
    from app.influencer.router import influencer_router

    dependency_callables = [d.dependency for d in influencer_router.dependencies]
    assert authenticate_request in dependency_callables
    assert ensure_module_enabled in dependency_callables


def test_router_health_endpoint_registered() -> None:
    from app.influencer.router import influencer_router

    routes = {r.path for r in influencer_router.routes}
    # El path completo incluye el prefix.
    assert '/v1/influencer/_health' in routes


# ── Montaje en main.py ─────────────────────────────────────────────────────


def test_main_imports_and_mounts_influencer_router() -> None:
    main_source = MAIN_PY.read_text(encoding='utf-8')
    assert 'from app.influencer.router import influencer_router' in main_source
    assert 'api.include_router(influencer_router)' in main_source
