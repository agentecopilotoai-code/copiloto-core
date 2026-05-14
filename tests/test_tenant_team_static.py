"""Static tests for TASK-0041 — Gestión de equipo y roles del tenant.

These tests inspect source files instead of spinning up the FastAPI app
so they can run in CI without Docker.  They verify that:
- the member endpoints exist, are scoped to admin and registered with
  ``require_min_role('admin')`` through ``tenant_admin_router``;
- the Auth0 management service exposes the helpers required by the
  backlog (token cache, invite, role assignment, revoke) and stays a
  no-op when not configured;
- the Admin Panel surfaces the Team module and Slack-style tenant
  switcher with the API helpers wired up.
"""
from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
SECURITY = Path('app/core/security.py')
AUTH0_ADMIN = Path('app/services/auth0_admin.py')

CORE_API = Path('admin-panel/src/services/coreApi.js')
MODULES = Path('admin-panel/src/data/modules.js')
TEAM_UI = Path('admin-panel/src/components/modules/team/TeamModule.jsx')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
SIDEBAR = Path('admin-panel/src/components/layout/Sidebar.jsx')


def test_member_endpoints_are_registered_under_admin_router():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/members')" in source
    assert "@tenant_admin_router.post(\n    '/tenants/{tenant_id}/members'" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/members/{user_id}')" in source
    assert "@tenant_admin_router.delete(\n    '/tenants/{tenant_id}/members/{user_id}'" in source


def test_tenant_admin_router_requires_admin_role():
    source = ROUTES.read_text()
    # The router is created with require_min_role('admin').
    assert "tenant_admin_router = APIRouter(" in source
    assert "Depends(require_min_role('admin'))" in source


def test_me_tenants_is_accessible_for_any_authenticated_user():
    source = ROUTES.read_text()
    # /me/tenants must not require admin (a viewer/agent should still
    # see the tenants they belong to to drive the Slack-style switcher).
    assert "@tenant_user_router.get('/me/tenants')" in source
    assert (
        "tenant_user_router = APIRouter(\n"
        "    tags=['tenant-user'],\n"
        "    dependencies=[Depends(authenticate_request)],\n"
        ")"
    ) in source
    assert 'router.include_router(tenant_user_router)' in source


def test_member_schemas_constrain_roles():
    source = SCHEMAS.read_text()
    assert 'class MemberInvite(BaseModel)' in source
    assert 'class MemberRoleUpdate(BaseModel)' in source
    # Cover every legal tenant role.
    for role in ('owner', 'admin', 'manager', 'agent', 'viewer'):
        assert role in source


def test_viewer_role_is_recognised_in_role_levels():
    assert "'viewer': 5" in SECURITY.read_text()


def test_member_routes_emit_audit_actions():
    source = ROUTES.read_text()
    for action in (
        'tenant_member.invited',
        'tenant_member.role_updated',
        'tenant_member.removed',
    ):
        assert action in source


def test_last_owner_cannot_be_demoted_or_removed():
    source = ROUTES.read_text()
    assert 'Cannot demote the last owner of the tenant' in source
    assert 'Cannot remove the last owner of the tenant' in source


def test_owner_role_can_only_be_assigned_by_owner():
    source = ROUTES.read_text()
    assert '_ensure_caller_can_target_role' in source
    assert "Only an owner can manage the owner role" in source


def test_auth0_admin_service_exposes_required_helpers():
    source = AUTH0_ADMIN.read_text()
    assert 'async def get_management_token' in source
    assert 'async def invite_user' in source
    assert 'async def assign_roles' in source
    assert 'async def revoke_tenant_roles' in source
    # Must short-circuit (no-op) when management credentials are missing.
    assert "auth0_management_enabled" in source
    assert "return {'disabled': True}" in source


def test_auth0_admin_uses_management_api_endpoints():
    source = AUTH0_ADMIN.read_text()
    # Password-change ticket for invitations.
    assert "'/tickets/password-change'" in source
    # PATCH /users/{id} keeps user_metadata in sync.
    assert "'/users/" in source


def test_invite_endpoint_marks_skip_when_auth0_disabled():
    source = ROUTES.read_text()
    assert 'auth0_skipped' in source
    assert 'auth0_management_enabled()' in source


def test_admin_panel_exposes_team_module():
    modules = MODULES.read_text()
    assert "id: 'team'" in modules
    # UI-005: minRole → capability de la matriz de permisos.
    assert "capability: 'team.write'" in modules

    layout = ADMIN_LAYOUT.read_text()
    assert "TeamModule" in layout
    assert "activeModuleId === 'team'" in layout
    # UI-005: el gate hasMinRole se reemplazó por <RequirePermission>.
    assert 'capability="team.write" mode="RW"' in layout

    api = CORE_API.read_text()
    for helper in (
        'listTenantMembers',
        'inviteTenantMember',
        'updateTenantMemberRole',
        'removeTenantMember',
    ):
        assert helper in api


def test_team_ui_supports_invite_and_role_change():
    ui = TEAM_UI.read_text()
    assert 'Invitar miembro' in ui
    assert 'inviteTenantMember' in ui
    assert 'updateTenantMemberRole' in ui
    assert 'removeTenantMember' in ui
    # Auth0 not-configured warning.
    assert 'Auth0 Management API no está habilitada' in ui


def test_sidebar_shows_slack_style_switcher():
    sidebar = SIDEBAR.read_text()
    assert 'tenant-switcher' in sidebar
    assert 'tenantOptions.map' in sidebar
    # Per-tenant role shown in the dropdown subtitle.
    assert 'tenant.role' in sidebar or 'tenant?.role' in sidebar


def test_admin_layout_persists_active_tenant_for_switching():
    layout = ADMIN_LAYOUT.read_text()
    assert "localStorage" in layout
    assert "copilotoia.activeTenantId" in layout
    # canSwitchTenants triggers whenever the user belongs to more than one tenant.
    assert 'tenantOptions.length > 1' in layout


def test_me_tenants_aggregates_roles_per_tenant():
    """The endpoint must return ``roles`` (plural) so the switcher can show
    multi-role memberships and the team module can pick the highest role."""
    source = ROUTES.read_text()
    # Snippet of the SQL aggregation that turns the join into one row per tenant.
    assert "array_agg(utr.role" in source
    assert "as roles" in source
