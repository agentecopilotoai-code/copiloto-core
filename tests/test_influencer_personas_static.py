"""Static checks para ``app/influencer/personas_router.py`` + migración
SQL — TASK-INFLU-008.

Verifica sin levantar DB:
- 5 endpoints declarados (list / get / create / patch / delete).
- DELETE exige ``require_mfa_for_privileged``.
- Migración SQL declara los CHECK constraints + indices + RLS policies.
- ``handle`` validator rechaza valores inválidos.
- Router montado en ``app.main``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.influencer.personas_models import (
    PersonaCreate,
    PersonaResponse,
    PersonaUpdate,
)
from app.influencer.personas_router import personas_router

SCHEMA_FILE = Path('infra/postgres/03-migrations.sql')
ROUTER_SOURCE = Path('app/influencer/personas_router.py').read_text(encoding='utf-8')


# ─── Router shape ──────────────────────────────────────────────────────────


def test_personas_router_has_5_endpoints():
    """list / get / create / patch / delete = 5 rutas."""
    paths = {(r.path, tuple(sorted(r.methods))) for r in personas_router.routes}
    assert any(p[0] == '/v1/influencer/personas' and 'GET' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/personas' and 'POST' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/personas/{persona_id}' and 'GET' in p[1] for p in paths)
    assert any(
        p[0] == '/v1/influencer/personas/{persona_id}' and 'PATCH' in p[1]
        for p in paths
    )
    assert any(
        p[0] == '/v1/influencer/personas/{persona_id}' and 'DELETE' in p[1]
        for p in paths
    )


def test_delete_requires_mfa_for_privileged():
    """El DELETE debe declarar `require_mfa_for_privileged` como dep."""
    assert 'require_mfa_for_privileged' in ROUTER_SOURCE
    # Más estricto: el DELETE específicamente debe tener la dep en su decorador.
    delete_block_idx = ROUTER_SOURCE.find('@personas_router.delete')
    assert delete_block_idx != -1
    # Tomamos los próximos ~600 chars que contienen el decorador + función.
    delete_block = ROUTER_SOURCE[delete_block_idx:delete_block_idx + 600]
    assert 'require_mfa_for_privileged' in delete_block


def test_router_inherits_auth_and_module_gate():
    """El router debe tener `authenticate_request` y `ensure_module_enabled`."""
    assert 'authenticate_request' in ROUTER_SOURCE
    assert 'ensure_module_enabled' in ROUTER_SOURCE


def test_create_persona_casts_jsonb_columns():
    """create_persona pasa los 5 campos jsonb como `::jsonb` casts.

    Regression: asyncpg rechaza dicts crudos con
    `DataError: expected str, got dict` cuando la columna es jsonb.
    El INSERT debe declarar `$N::jsonb` para face/body/identity/voice/platforms
    y usar `json.dumps()` para serializar los valores.
    """
    insert_start = ROUTER_SOURCE.find('insert into influencer.personas')
    assert insert_start != -1, 'INSERT de create_persona no encontrado'
    insert_end = ROUTER_SOURCE.find('returning *', insert_start)
    insert_block = ROUTER_SOURCE[insert_start:insert_end]
    # Debe haber 5 casts ::jsonb (uno por cada columna jsonb).
    assert insert_block.count('::jsonb') >= 5, (
        f'Esperaba 5 casts ::jsonb, encontré {insert_block.count("::jsonb")}'
    )
    # Y el módulo debe importar json para serializar.
    assert 'import json' in ROUTER_SOURCE
    assert 'json.dumps(body.face)' in ROUTER_SOURCE


def test_patch_persona_casts_jsonb_columns_when_updated():
    """patch_persona también debe castear jsonb (mismo bug de asyncpg)."""
    # El loop de updates debe detectar columnas jsonb y emitir `::jsonb`.
    assert "_JSONB_COLS" in ROUTER_SOURCE or "'face', 'body', 'identity'" in ROUTER_SOURCE
    assert '::jsonb' in ROUTER_SOURCE


def test_jsonb_to_dict_decodes_string_payloads():
    """Regression: asyncpg sin codec global devuelve jsonb como string,
    y PersonaResponse rechaza str con `Input should be a valid dictionary`.
    _jsonb_to_dict debe normalizar str → dict, None → {}, dict → dict.
    """
    from app.influencer.personas_router import _jsonb_to_dict

    assert _jsonb_to_dict(None) == {}
    assert _jsonb_to_dict('') == {}
    assert _jsonb_to_dict('{}') == {}
    assert _jsonb_to_dict('{"a": 1}') == {'a': 1}
    assert _jsonb_to_dict({'a': 1}) == {'a': 1}


def test_router_mounted_in_app_main():
    """El router debe estar incluido en `app/main.py`."""
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'personas_router' in main_src
    assert 'include_router(influencer_personas_router)' in main_src


# ─── Pydantic models ───────────────────────────────────────────────────────


def test_handle_validator_rejects_invalid():
    # Handles inválidos después de lower(): demasiado cortos, char no permitido,
    # empieza con underscore, contiene dash o espacio, demasiado largos.
    for bad in ('ab', '_starts_with_under', 'has space', 'has-dash', 'a' * 31):
        with pytest.raises(ValueError):
            PersonaCreate(name='X', handle=bad)


def test_handle_validator_normalizes_to_lower():
    """Acepta `MyHandle` y lo guarda como `myhandle` (case-insensitive)."""
    p = PersonaCreate(name='Sofia', handle='MyHandle')
    assert p.handle == 'myhandle'
    p2 = PersonaCreate(name='X', handle='UPPERCASE')
    assert p2.handle == 'uppercase'


def test_persona_create_defaults_status_draft():
    p = PersonaCreate(name='X', handle='abc123')
    assert p.status == 'draft'
    assert p.mode == 'manual_approval'
    assert p.disclose_ai is True


def test_persona_update_all_fields_optional():
    # Empty body OK
    PersonaUpdate()
    PersonaUpdate(name='New')


def test_persona_response_from_attributes_enabled():
    """`from_attributes=True` permite construir desde asyncpg.Record / objetos."""
    assert PersonaResponse.model_config.get('from_attributes') is True


# ─── Migración SQL ─────────────────────────────────────────────────────────


def _sql() -> str:
    return SCHEMA_FILE.read_text(encoding='utf-8')


def test_migration_creates_personas_table():
    sql = _sql()
    assert 'create table if not exists influencer.personas' in sql


def test_migration_declares_status_check():
    sql = _sql()
    assert "status in ('draft', 'active', 'paused', 'archived')" in sql


def test_migration_declares_mode_check():
    sql = _sql()
    assert "mode in ('auto_generate', 'manual_approval', 'hybrid')" in sql


def test_migration_unique_handle_per_tenant():
    sql = _sql()
    assert 'ux_personas_tenant_handle_lower' in sql
    assert 'lower(handle)' in sql


def test_migration_index_for_listing():
    sql = _sql()
    assert 'ix_personas_tenant_status_created' in sql


def test_migration_rls_enabled():
    sql = _sql()
    assert 'alter table influencer.personas enable row level security' in sql
    assert 'personas_tenant_isolation' in sql
    assert 'personas_tenant_write' in sql


def test_migration_archive_column_exists():
    """Soft-delete via `archived_at` (no DROP)."""
    sql = _sql()
    # Buscar la línea donde se declara archived_at en el bloque de personas.
    personas_block_start = sql.find('create table if not exists influencer.personas')
    assert personas_block_start > 0
    end = sql.find(');', personas_block_start)
    block = sql[personas_block_start:end]
    assert 'archived_at' in block
