"""Tests para `app.gd.bootstrap.bootstrap_gd_for_tenant`.

Cubre el hook estructural que el PATCH ``/v1/platform/tenant-modules/
{tenant_id}/gestion_documental`` invoca al activar el módulo:

1. Seed idempotente de los 19 roles GD del sistema.
2. INSERT de gd.perfil_usuario con estado_gd=activo para cada owner/admin.
3. INSERT de gd.asignacion_alcance con rol gd.admin_sistema y alcance global.
4. Idempotencia — re-correr no duplica filas.
5. Métricas correctas en el dict de retorno.

Mocks de asyncpg.Connection — no requiere DB real.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.bootstrap import (
    _GD_SYSTEM_ROLES,
    _TENANT_ROLES_FOR_AUTO_BOOTSTRAP,
    bootstrap_gd_for_tenant,
)


def _make_conn(
    *,
    seed_inserted: int = 0,  # cuántos roles devuelven 'INSERT 0 1'
    owners: list[dict] | None = None,
    actor_user_id: str | None = None,
    actor_exists_in_app_users: bool = True,
    perfil_created_for: set[str] | None = None,
    asignacion_existing_for: set[str] | None = None,
) -> AsyncMock:
    """Construye un AsyncMock que simula la secuencia de queries del bootstrap.

    Secuencia esperada (ver `bootstrap_gd_for_tenant`):
      1. execute(INSERT gd.rol) × len(_GD_SYSTEM_ROLES) — controlado por seed_inserted
      2. fetch(SELECT owners) → owners
      3. Si actor_user_id NO está en owners: fetchrow(SELECT 1 FROM app.users)
         para verificar que el actor existe.
      4. Por user (owners + posiblemente actor):
         a. fetchrow(INSERT/UPDATE gd.perfil_usuario) → {'created': True/False}
         b. fetchrow(SELECT gd.asignacion_alcance existente) → None o {'id': ...}
         c. execute(INSERT gd.asignacion_alcance) — solo si no existía
    """
    conn = AsyncMock()

    # 1. execute para gd.rol: primero `seed_inserted` devuelven 'INSERT 0 1';
    #    el resto devuelve 'INSERT 0 0'.
    execute_results: list[str] = (
        ['INSERT 0 1'] * seed_inserted
        + ['INSERT 0 0'] * (len(_GD_SYSTEM_ROLES) - seed_inserted)
    )

    # 2. fetch para listar owners — un solo `fetch` en todo el flow.
    fetch_results: list[list[dict]] = [owners or []]

    owner_ids = {str(o['user_id']) for o in (owners or [])}

    fetchrow_results: list[dict | None] = []

    # 3. Si actor_user_id se pasa y NO está en owners, el bootstrap
    #    pregunta a app.users si existe → fetchrow.
    will_bootstrap_actor = False
    if actor_user_id and actor_user_id not in owner_ids:
        fetchrow_results.append({'?column?': 1} if actor_exists_in_app_users else None)
        if actor_exists_in_app_users:
            will_bootstrap_actor = True

    # 4. Por user (owners + actor si aplica) — UPSERT perfil + check asignación.
    target_users = list(owner_ids)
    if will_bootstrap_actor:
        target_users.append(actor_user_id)

    perfil_created_for = perfil_created_for or set()
    asignacion_existing_for = asignacion_existing_for or set()
    for uid in target_users:
        # a. UPSERT perfil_usuario.
        fetchrow_results.append({'created': uid in perfil_created_for})
        # b. SELECT asignacion existente.
        if uid in asignacion_existing_for:
            fetchrow_results.append({'id': str(uuid4())})
        else:
            fetchrow_results.append(None)
            # c. Si no existía, se hace INSERT (execute).
            execute_results.append('INSERT 0 1')

    conn.execute.side_effect = execute_results
    conn.fetch.side_effect = fetch_results
    conn.fetchrow.side_effect = fetchrow_results
    return conn


@pytest.mark.asyncio
class TestBootstrapGdForTenant:
    async def test_seed_19_roles_cuando_db_vacia(self) -> None:
        """Primera activación: los 19 roles se insertan, no hay owners
        ni actor → no se bootstrappa ningún user."""
        conn = _make_conn(seed_inserted=19, owners=[], actor_user_id=None)
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=None,
        )
        assert result['roles_seeded'] == 19
        assert result['perfiles_creados'] == 0
        assert result['asignaciones_creadas'] == 0
        assert result['users_boostrapped'] == []
        # 19 execute para gd.rol exactamente.
        assert conn.execute.await_count == 19

    async def test_seed_idempotente_cuando_ya_existen(self) -> None:
        """Re-activación: los 19 roles ya están, 0 inserts."""
        conn = _make_conn(seed_inserted=0, owners=[], actor_user_id=None)
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=None,
        )
        assert result['roles_seeded'] == 0

    async def test_crea_perfil_y_asignacion_para_owner(self) -> None:
        """Owner sin perfil ni asignación → ambos se crean."""
        owner_id = uuid4()
        owners = [{'user_id': owner_id, 'email': 'o@x.co', 'display_name': 'O'}]
        actor_id = str(owner_id)  # actor == owner → no extra fetchrow
        conn = _make_conn(
            seed_inserted=0,
            owners=owners,
            actor_user_id=actor_id,
            perfil_created_for={str(owner_id)},
            asignacion_existing_for=set(),
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=actor_id,
        )
        assert result['perfiles_creados'] == 1
        assert result['asignaciones_creadas'] == 1
        assert result['users_boostrapped'] == [str(owner_id)]

    async def test_no_duplica_asignacion_existente(self) -> None:
        """Owner con gd.admin_sistema ya activa → asignaciones_creadas=0."""
        owner_id = uuid4()
        owners = [{'user_id': owner_id, 'email': 'o@x.co', 'display_name': 'O'}]
        conn = _make_conn(
            seed_inserted=0,
            owners=owners,
            actor_user_id=str(owner_id),
            perfil_created_for=set(),
            asignacion_existing_for={str(owner_id)},
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=str(owner_id),
        )
        assert result['perfiles_creados'] == 0
        assert result['asignaciones_creadas'] == 0
        assert result['users_boostrapped'] == [str(owner_id)]

    async def test_multiples_owners(self) -> None:
        """N owners → N perfiles + N asignaciones (actor es uno de ellos)."""
        owners = [
            {'user_id': uuid4(), 'email': f'u{i}@x.co', 'display_name': f'U{i}'}
            for i in range(3)
        ]
        actor_id = str(owners[0]['user_id'])
        conn = _make_conn(
            seed_inserted=0,
            owners=owners,
            actor_user_id=actor_id,
            perfil_created_for={str(o['user_id']) for o in owners},
            asignacion_existing_for=set(),
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=actor_id,
        )
        assert result['perfiles_creados'] == 3
        assert result['asignaciones_creadas'] == 3
        assert len(result['users_boostrapped']) == 3

    async def test_actor_user_id_none_no_falla(self) -> None:
        """actor_user_id=None es legal (ej. seed desde sistema)."""
        owner_id = uuid4()
        conn = _make_conn(
            seed_inserted=0,
            owners=[{'user_id': owner_id, 'email': 'o@x.co', 'display_name': 'O'}],
            actor_user_id=None,
            perfil_created_for={str(owner_id)},
            asignacion_existing_for=set(),
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=None,
        )
        assert result['perfiles_creados'] == 1

    async def test_actor_no_owner_se_incluye_en_bootstrap(self) -> None:
        """Caso platform_owner support_mode: actor NO está en owners del tenant
        → bootstrap igual le crea perfil + admin_sistema. Sin este behavior,
        el platform_owner entra al módulo y ve "SIN ROL"."""
        owner_id = uuid4()
        actor_id = str(uuid4())  # distinto de owners → debe agregarse
        conn = _make_conn(
            seed_inserted=0,
            owners=[{'user_id': owner_id, 'email': 'o@x.co', 'display_name': 'O'}],
            actor_user_id=actor_id,
            actor_exists_in_app_users=True,
            perfil_created_for={str(owner_id), actor_id},
            asignacion_existing_for=set(),
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=actor_id,
        )
        assert result['perfiles_creados'] == 2
        assert result['asignaciones_creadas'] == 2
        assert set(result['users_boostrapped']) == {str(owner_id), actor_id}

    async def test_actor_inexistente_en_app_users_se_omite(self) -> None:
        """Si el actor_user_id pasado no corresponde a un user real
        (caso edge: UUID bogus), no falla el bootstrap, solo lo omite."""
        owner_id = uuid4()
        actor_id = str(uuid4())
        conn = _make_conn(
            seed_inserted=0,
            owners=[{'user_id': owner_id, 'email': 'o@x.co', 'display_name': 'O'}],
            actor_user_id=actor_id,
            actor_exists_in_app_users=False,  # ← clave
            perfil_created_for={str(owner_id)},
            asignacion_existing_for=set(),
        )
        result = await bootstrap_gd_for_tenant(
            conn, tenant_id=str(uuid4()), actor_user_id=actor_id,
        )
        assert result['perfiles_creados'] == 1
        assert result['users_boostrapped'] == [str(owner_id)]

    async def test_query_owners_filtra_por_roles_correctos(self) -> None:
        """SELECT de owners debe filtrar por role IN ('owner', 'admin')."""
        conn = _make_conn(seed_inserted=0, owners=[], actor_user_id=None)
        tenant_id = str(uuid4())
        await bootstrap_gd_for_tenant(
            conn, tenant_id=tenant_id, actor_user_id=None,
        )
        # Verifica que el call a fetch incluya los roles correctos.
        fetch_call = conn.fetch.call_args
        sql_arg = fetch_call.args[0]
        roles_arg = fetch_call.args[2]
        assert 'app.user_tenant_roles' in sql_arg
        assert roles_arg == list(_TENANT_ROLES_FOR_AUTO_BOOTSTRAP)
        assert fetch_call.args[1] == tenant_id


class TestGdSystemRolesCatalog:
    """Sanity checks sobre el catálogo `_GD_SYSTEM_ROLES`."""

    def test_19_roles_exactos(self) -> None:
        # La Matriz de Roles del PDF Doc 3 define exactamente 19 roles seed.
        assert len(_GD_SYSTEM_ROLES) == 19

    def test_admin_sistema_presente(self) -> None:
        # Debe existir el rol que el bootstrap asigna automáticamente.
        codigos = {r[0] for r in _GD_SYSTEM_ROLES}
        assert 'gd.admin_sistema' in codigos

    def test_codigos_unicos(self) -> None:
        codigos = [r[0] for r in _GD_SYSTEM_ROLES]
        assert len(codigos) == len(set(codigos))

    def test_todos_los_codigos_son_gd_prefix(self) -> None:
        for codigo, _, _ in _GD_SYSTEM_ROLES:
            assert codigo.startswith('gd.'), f'rol sin prefijo gd.: {codigo!r}'
