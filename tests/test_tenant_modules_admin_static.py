"""Static tests para los endpoints platform_admin de tenant_modules — TASK-INFLU-019."""
from __future__ import annotations

from pathlib import Path

from app.api.v1.routes import platform_admin_router
from app.influencer.admin_routes import (
    TenantModuleListResponse,
    TenantModuleRow,
    TenantModuleUpdate,
)


SRC = Path('app/influencer/admin_routes.py').read_text(encoding='utf-8')


def test_endpoints_mounted_on_platform_admin_router():
    """GET + PATCH bajo /platform/tenant-modules en platform_admin_router."""
    paths = {(r.path, tuple(sorted(r.methods))) for r in platform_admin_router.routes}
    assert any('tenant-modules' in p[0] and 'GET' in p[1] for p in paths)
    assert any('tenant-modules' in p[0] and 'PATCH' in p[1] for p in paths)


def test_set_support_mode_before_queries():
    """Ambos endpoints setean app.support_mode='true' para bypassear RLS."""
    assert '_set_support_mode(conn, True)' in SRC
    assert "'app.support_mode'" in SRC


def test_audit_emitted_only_when_activated_changed():
    assert 'await audit(' in SRC
    assert 'platform.tenant_module.activated' in SRC
    assert 'platform.tenant_module.deactivated' in SRC


def test_audit_metadata_excludes_notes_content():
    """notes_provided: bool (presencia), pero NO el contenido literal.

    El audit del endpoint de tenant_modules está después de
    `platform.tenant_module.activated` action — busca ese bloque.
    """
    marker = 'platform.tenant_module.activated'
    idx = SRC.find(marker)
    assert idx > 0
    # 600 chars alrededor del action cubren todo el metadata dict.
    block = SRC[idx:idx + 800]
    assert 'notes_provided' in block
    # El contenido NO debe aparecer como key 'notes': en el metadata
    assert "'notes':" not in block


def test_body_schema_has_notes_with_max_length():
    src = Path('app/influencer/admin_routes.py').read_text(encoding='utf-8')
    # Buscar el class TenantModuleUpdate
    idx = src.find('class TenantModuleUpdate')
    assert idx > 0
    class_body = src[idx:idx + 500]
    assert 'notes' in class_body
    assert 'max_length=500' in class_body


def test_cache_invalidate_called_after_patch():
    assert '_module_gate_cache_invalidate()' in SRC
    assert '_cache_invalidate as _module_gate_cache_invalidate' in SRC


def test_preflight_409_when_providers_not_configured():
    """Para module='influencer' + enabled=True, exige providers configurados."""
    assert "module == 'influencer' and body.enabled is True" in SRC
    assert 'ai_providers_not_configured' in SRC
    assert 'HTTP_409_CONFLICT' in SRC


def test_required_modalities_at_least_llm_and_image():
    from app.influencer.admin_routes import _REQUIRED_MODALITIES_FOR_INFLUENCER
    assert 'llm' in _REQUIRED_MODALITIES_FOR_INFLUENCER
    assert 'image' in _REQUIRED_MODALITIES_FOR_INFLUENCER


def test_pydantic_models_declared():
    assert TenantModuleRow.model_fields
    assert TenantModuleListResponse.model_fields
    assert TenantModuleUpdate.model_fields


def test_update_body_requires_enabled():
    """`enabled` es required (sin default)."""
    field = TenantModuleUpdate.model_fields['enabled']
    assert field.is_required()


def test_unknown_tenant_returns_404():
    assert 'tenant not found' in SRC
    assert 'HTTP_404_NOT_FOUND' in SRC


def test_unknown_module_returns_400():
    """CheckViolationError → 400 con detail útil."""
    assert 'CheckViolationError' in SRC
    assert 'HTTP_400_BAD_REQUEST' in SRC


def test_idempotent_patch_does_not_reset_activated_at():
    """Si enabled no cambia, solo update plan/notes — NO activated_at."""
    assert 'activated_changed' in SRC
    # En el branch idempotente, solo update plan y notes (no activated_at).
    # BUGFIX-RLS-TXN — el cuerpo ahora vive dentro de
    # `async with conn.transaction():`, así que la indentación del SQL
    # subió un nivel. Comparamos modulo whitespace para no acoplar el test
    # a la profundidad exacta de indentación.
    import re
    normalised = re.sub(r'\s+', ' ', SRC)
    assert 'update app.tenant_modules set plan' in normalised


def test_update_tenant_module_runs_inside_explicit_transaction():
    """BUGFIX-RLS-TXN — el handler ``update_tenant_module`` debe envolver
    ``set_config('app.support_mode', 'true', true)`` + INSERT/UPDATE en un
    ``async with conn.transaction():``. Sin la transacción explícita el
    setting es transaction-local y se descarta antes del INSERT, así que
    RLS rechaza la escritura con ``InsufficientPrivilegeError``. Verificamos
    la presencia del bloque en el código fuente del handler.
    """
    idx = SRC.find('async def update_tenant_module')
    assert idx > 0
    # 2500 chars cubren el cuerpo entero del handler.
    body = SRC[idx:idx + 2500]
    assert 'async with conn.transaction():' in body, (
        'update_tenant_module DEBE correr todo dentro de '
        '`async with conn.transaction():` para anclar `set_config(..., true)` '
        'al ciclo de vida del INSERT.'
    )


def test_list_tenant_modules_runs_inside_explicit_transaction():
    """Mismo contrato para el GET — mantiene patrón consistente con el PATCH."""
    idx = SRC.find('async def list_tenant_modules')
    assert idx > 0
    body = SRC[idx:idx + 2500]
    assert 'async with conn.transaction():' in body
