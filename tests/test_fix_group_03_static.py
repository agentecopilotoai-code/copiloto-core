"""Fix-group 03: BUG-033..BUG-037 — Auth0 cluster + role mismatches UI↔backend.

- BUG-033: NOT-APPLICABLE — `configure-auth0.sh` ya crea el Management API
  client grant (líneas 286-295) cuando se mergeó el BUG-001 fix.
- BUG-034: RESOLVED-IN-FOLLOWUP — BUG-009 fix usa `verify_email: True`
  en `POST /users` lo que dispara el email template de Auth0 que entrega
  el ticket al invitee.
- BUG-035: RESOLVED-IN-FOLLOWUP — BUG-009 fix llama
  `set_user_tenant_metadata` + `assign_auth0_role_by_name` entre crear
  user y emitir ticket. La PostLogin Action lee `app_metadata.tenant_id`
  y `event.authorization.roles` para emitir los claims al JWT.
- BUG-036: VIGENTE. Digest CRUD vivían en `tenant_admin_router` (admin+)
  pero la UI los expone con `digest.write` (manager+). Fix: nuevo
  `tenant_manager_router` con `require_min_role('manager')` y los 4
  endpoints de digest migrados ahí.
- BUG-037: VIGENTE. `tenant_analytics_router` requería `manager` pero
  ViewerAnalytics (UI-010.2) reusa `AnalyticsPanel` con capability
  `analytics.tenant.read` (viewer). Fix: bajado el gate a `viewer`.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.api.v1 import routes as routes_module


CONFIGURE_AUTH0 = Path('scripts/configure-auth0.sh')
AUTH0_ADMIN = Path('app/services/auth0_admin.py')


def _source_of(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(routes_module, name)))


# ───── BUG-033 — NOT-APPLICABLE (Management API grant ya creado) ─────────


def test_bug_033_configure_auth0_creates_mgmt_api_client_grant():
    """El script debe contener la lógica de upsert del client_grant para la
    Management API audience.
    """
    src = CONFIGURE_AUTH0.read_text()
    assert 'MGMT_API_AUDIENCE="https://${AUTH0_DOMAIN}/api/v2/"' in src, (
        'BUG-033: regresión — script no define `MGMT_API_AUDIENCE` apuntando '
        'a la Management API.'
    )
    assert 'MGMT_API_SCOPES=' in src, (
        'BUG-033: regresión — script no define `MGMT_API_SCOPES`.'
    )
    assert 'create:user_tickets' in src, (
        'BUG-033: scope `create:user_tickets` requerido para emitir el ticket '
        'de password-change. `read:tickets` NO sirve (es otro scope).'
    )
    assert "api_post '/client-grants'" in src, (
        'BUG-033: el script debe crear el client_grant si no existe.'
    )


# ───── BUG-034 / BUG-035 — RESOLVED-IN-FOLLOWUP (BUG-009 flow) ───────────


def test_bug_034_invite_uses_verify_email_for_delivery():
    """`invite_user` debe pasar `verify_email: True` para que Auth0 dispare
    su email template y entregue el ticket de password-change al invitee.
    Sin esto, el ticket queda solo en logs y el invitee nunca puede acceder.
    """
    src = AUTH0_ADMIN.read_text()
    assert "'verify_email': True" in src, (
        'BUG-034: `invite_user` debe pasar `verify_email: True` en el POST '
        '/users — sin esto Auth0 NO manda el email de invitación, el ticket '
        'queda en logs y el invitee no puede setear su password.'
    )


def test_bug_035_invite_propagates_tenant_metadata_and_role():
    """`invite_user` debe llamar `set_user_tenant_metadata` Y
    `assign_auth0_role_by_name` ENTRE crear el user y emitir el ticket.
    Sin esto, el JWT post-login no trae `tenant_id` claim ni roles, y el
    panel rechaza al invitee.
    """
    src = AUTH0_ADMIN.read_text()
    assert 'await set_user_tenant_metadata(' in src, (
        'BUG-035: `invite_user` debe llamar `set_user_tenant_metadata` para '
        'poblar `app_metadata.tenant_id` (leído por la PostLogin Action).'
    )
    assert 'await assign_auth0_role_by_name(' in src, (
        'BUG-035: `invite_user` debe llamar `assign_auth0_role_by_name` para '
        'asignar el rol Auth0 (leído por `event.authorization.roles`).'
    )


# ───── BUG-036 — digest endpoints en manager router ──────────────────────


def test_bug_036_tenant_manager_router_exists():
    """Nuevo router con `require_min_role('manager')` para endpoints que la
    UI expone a managers pero que estaban en `tenant_admin_router`.
    """
    assert hasattr(routes_module, 'tenant_manager_router'), (
        'BUG-036: el router `tenant_manager_router` debe existir en routes.py.'
    )


def test_bug_036_digest_endpoints_on_manager_router():
    """Los 4 endpoints de digest subscriptions deben colgar de
    `tenant_manager_router`, no de `tenant_admin_router`.
    """
    full_src = inspect.getsource(routes_module)
    # 4 decoradores esperados en el manager router.
    expected_decorators = [
        "@tenant_manager_router.get('/tenants/{tenant_id}/digest/subscriptions')",
        "@tenant_manager_router.post(\n    '/tenants/{tenant_id}/digest/subscriptions'",
        "@tenant_manager_router.patch(\n    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}'",
        "@tenant_manager_router.delete(\n    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}'",
    ]
    for decorator in expected_decorators:
        assert decorator in full_src, (
            f'BUG-036: falta el decorador esperado:\n{decorator}\n'
            f'Los 4 endpoints de digest CRUD deben estar en `tenant_manager_router`.'
        )
    # Ninguno debe seguir colgando de tenant_admin_router.
    forbidden = [
        "@tenant_admin_router.get('/tenants/{tenant_id}/digest/subscriptions')",
        "@tenant_admin_router.post(\n    '/tenants/{tenant_id}/digest/subscriptions'",
        "@tenant_admin_router.patch(\n    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}'",
        "@tenant_admin_router.delete(\n    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}'",
    ]
    for decorator in forbidden:
        assert decorator not in full_src, (
            f'BUG-036: regresión — un endpoint de digest volvió a '
            f'`tenant_admin_router`:\n{decorator}\n'
            'Los managers vuelven a recibir 403 al intentar gestionar suscripciones.'
        )


def test_bug_036_manager_router_registered_in_app():
    """El nuevo router debe estar registrado via `router.include_router(...)`
    en routes.py — sin esto, las rutas existen como decoradores pero NUNCA
    se montan en FastAPI y todas devuelven 404.
    """
    full_src = inspect.getsource(routes_module)
    assert 'router.include_router(tenant_manager_router)' in full_src, (
        'BUG-036: regresión — `tenant_manager_router` no se registra con '
        '`router.include_router(...)`. Los endpoints de digest devolverán 404.'
    )


# ───── BUG-037 — tenant_analytics_router bajado a viewer ─────────────────


def test_bug_037_tenant_analytics_router_allows_viewer():
    """El router debe requerir `viewer` (no `manager`) para que UI-010.2
    `ViewerAnalytics` (que monta `AnalyticsPanel` con capability
    `analytics.tenant.read`) pueda consumir los endpoints.
    """
    full_src = inspect.getsource(routes_module)
    # Aislar el bloque del router: desde `tenant_analytics_router = APIRouter(`
    # hasta el siguiente `^tenant_` o el final de la sección. Usar
    # `find()` por `)` no sirve porque los comentarios incluyen paréntesis
    # de URLs y matchean antes que el cierre real del APIRouter(...).
    block_idx = full_src.find('tenant_analytics_router = APIRouter(')
    assert block_idx > 0, 'BUG-037: el router debe existir.'
    # Tomar hasta el siguiente router (tenant_manager_router) o 600 chars,
    # lo que venga primero — alcanza para cubrir `dependencies=[...]\n)`.
    block_end_marker = full_src.find('tenant_manager_router', block_idx)
    block_end = block_end_marker if block_end_marker > 0 else block_idx + 600
    block = full_src[block_idx:block_end]
    assert "require_min_role('viewer')" in block, (
        'BUG-037: `tenant_analytics_router` debe requerir `viewer` (no '
        '`manager`) para que ViewerAnalytics pueda consumir los endpoints. '
        'Todos los routes aquí son GETs read-only.'
    )
    # El bloque del router puede mencionar `manager` en el comentario explicativo
    # del fix; lo que NO queremos es la dependencia activa.
    dependencies_line_idx = block.find('dependencies=')
    assert dependencies_line_idx > 0, (
        'BUG-037: el router debe declarar `dependencies=[...]`.'
    )
    dependencies_line = block[dependencies_line_idx:block.find('\n', dependencies_line_idx)]
    assert "require_min_role('manager')" not in dependencies_line, (
        'BUG-037: regresión — el router volvió a requerir `manager` en la '
        'línea de dependencies. ViewerAnalytics vuelve a recibir 403.'
    )
