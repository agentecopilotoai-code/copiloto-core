"""Fix-group 19: BUG-113..BUG-117.

- BUG-113: VIGENTE. El AlertBanner del error de `Packages` quedaba detrás
  del backdrop del `PackageFormModal` cuando el modal estaba abierto, así
  que un save-fail no daba feedback visible. Fix: pasar `error` +
  `onDismissError` al modal y renderizar AlertBanner inline en el body.
- BUG-114: NOT-APPLICABLE. Las 4 mutaciones de services
  (`POST/PATCH/DELETE/reorder /tenants/{id}/services{,/...}`) ya están
  en `tenant_admin_router` (admin+ MFA). La matriz dice `services.write
  = admin/owner only`, así que backend y matriz coinciden — viewer y
  agent ya están bloqueados.
- BUG-115: VIGENTE. `ContactPackagesPanel.onRefund` disparaba el refund
  directo sin confirm. Regresión vs `ContactsModule` legacy.
  Fix: `useConfirm` + handler `handleRefund` que pide confirmación
  antes de invocar `onRefund`.
- BUG-116: VIGENTE. `useContactsData` solo limpiaba `consent` cuando
  `selectedContactId` caía a null; `profile` y `contactPackages` se
  quedaban del contacto anterior (visible al hacer tenant switch).
  Fix: limpiar `setProfile(null)` y `setContactPackages([])` también.
- BUG-117: VIGENTE. `dashboard` declaraba `capability: 'analytics.tenant.read'`
  (R para viewer/agent/manager también), pero por spec es Owner/Admin-only.
  Fix: nueva capability `dashboard.read` (admin/owner=R) en matrix.js +
  módulo `dashboard` apunta a ella + `categorizeCapability` cubre el dominio.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


PACKAGES = Path('admin-panel/src/features/owner-admin/packages/Packages.jsx')
PACKAGE_MODAL = Path('admin-panel/src/features/owner-admin/packages/components/PackageFormModal.jsx')
CONTACT_PACKAGES_PANEL = Path(
    'admin-panel/src/features/owner-admin/conversations-contacts/components/ContactPackagesPanel.jsx'
)
USE_CONTACTS_DATA = Path(
    'admin-panel/src/features/owner-admin/conversations-contacts/hooks/useContactsData.js'
)
MATRIX = Path('admin-panel/src/permissions/matrix.js')
MODULES = Path('admin-panel/src/app/modules.js')
ROLES_ACL_DATA = Path('admin-panel/src/features/platform/roles-acl/rolesAclData.js')
# ───── BUG-113 — error inline en el modal ────────────────────────────────


def test_bug_113_package_form_modal_renders_error_inline():
    src = PACKAGE_MODAL.read_text()
    # Acepta `error` + `onDismissError` props.
    assert 'error,' in src and 'onDismissError,' in src, (
        'BUG-113: el modal debe aceptar `error` + `onDismissError` props.'
    )
    # Importa AlertBanner del ui index.
    assert 'AlertBanner' in src, 'BUG-113: AlertBanner debe importarse en el modal.'
    # Renderiza el AlertBanner dentro del form (tone danger).
    assert '<AlertBanner' in src and 'tone="danger"' in src, (
        'BUG-113: el modal debe renderizar `<AlertBanner tone="danger" title={error}>` '
        'inline en el body, para que se vea por encima del backdrop.'
    )


def test_bug_113_packages_passes_error_to_modal():
    src = PACKAGES.read_text()
    # El outer pasa error solo cuando el modal está abierto, para no duplicar feedback.
    assert 'error={state.modalOpen ? state.error : ' in src, (
        'BUG-113: Packages debe pasar `error={state.modalOpen ? state.error : ...}` '
        'al PackageFormModal para que el feedback inline aparezca al fallar el save.'
    )
    assert 'onDismissError={actions.dismissError}' in src, (
        'BUG-113: Packages debe pasar `onDismissError={actions.dismissError}`.'
    )


# ───── BUG-115 — confirm antes del refund ────────────────────────────────


def test_bug_115_contact_packages_panel_confirms_before_refund():
    src = CONTACT_PACKAGES_PANEL.read_text()
    assert 'useConfirm' in src, (
        'BUG-115: `ContactPackagesPanel` debe importar `useConfirm`.'
    )
    assert 'handleRefund' in src, (
        'BUG-115: debe existir un handler `handleRefund` que pide confirmación '
        'antes de invocar `onRefund`.'
    )
    # El refund button ahora dispara handleRefund, no onRefund directo.
    assert 'onClick={() => handleRefund(pkg.id' in src, (
        'BUG-115: el botón Reembolsar debe invocar `handleRefund`, no `onRefund` directo.'
    )
    # El confirm pasa danger:true (acción irreversible).
    assert 'danger: true' in src, (
        'BUG-115: el `confirm` del refund debe llevar `danger: true` '
        '(acción irreversible que afecta al pago).'
    )


# ───── BUG-116 — limpiar profile/packages en deselect ────────────────────


def test_bug_116_use_contacts_data_clears_profile_and_packages_on_deselect():
    src = USE_CONTACTS_DATA.read_text()
    # Encontrar el bloque del else (cuando selectedContactId es null).
    eff_idx = src.find('useEffect(() => {\n    if (selectedContactId)')
    assert eff_idx > 0
    next_block = src.find('\n  async function', eff_idx)
    block = src[eff_idx:next_block]
    # Sin el fix, solo había `setConsent(null)` — ahora debe haber tres setters.
    assert 'setProfile(null)' in block, (
        'BUG-116: cuando `selectedContactId` cae a null, debe llamarse '
        '`setProfile(null)` (antes solo se limpiaba consent → drawer mostraba '
        'profile stale del contacto anterior).'
    )
    assert 'setContactPackages([])' in block, (
        'BUG-116: también `setContactPackages([])` debe limpiarse al deselect, '
        'sino el drawer muestra packages del contacto anterior.'
    )
    assert 'setConsent(null)' in block, (
        'BUG-116: la limpieza de `consent` no debe perderse.'
    )


# ───── BUG-117 — dashboard.read restringido a admin/owner ────────────────


def test_bug_117_matrix_declares_dashboard_read_admin_owner_only():
    src = MATRIX.read_text()
    # La nueva cap existe.
    line_idx = src.find("'dashboard.read':")
    assert line_idx > 0, (
        'BUG-117: matrix.js debe declarar `dashboard.read` para que el módulo '
        'dashboard quede Owner/Admin-only (antes usaba `analytics.tenant.read`, '
        'visible a viewer/agent/manager también).'
    )
    # Solo admin y owner deben tener acceso (R), el resto null.
    eol = src.find('\n', line_idx)
    line = src[line_idx:eol]
    assert 'viewer: null' in line, 'BUG-117: viewer no debe ver dashboard.'
    assert 'agent: null' in line, 'BUG-117: agent no debe ver dashboard.'
    assert 'manager: null' in line, (
        'BUG-117: manager no debe ver dashboard (usa `manager-analytics`).'
    )
    assert 'admin: R' in line, 'BUG-117: admin debe poder leer dashboard.'
    assert 'owner: R' in line, 'BUG-117: owner debe poder leer dashboard.'


def test_bug_117_dashboard_module_uses_dashboard_read_capability():
    src = MODULES.read_text()
    dash_idx = src.find("id: 'dashboard',")
    assert dash_idx > 0
    # Buscar el `capability:` del bloque dashboard (siguiente cierre `},`).
    next_close = src.find('\n  },', dash_idx)
    block = src[dash_idx:next_close]
    assert "capability: 'dashboard.read'" in block, (
        'BUG-117: el módulo `dashboard` debe usar `dashboard.read`, no '
        '`analytics.tenant.read` (que también tienen viewer/agent/manager).'
    )


def test_bug_117_roles_acl_categorizes_dashboard_domain():
    src = ROLES_ACL_DATA.read_text()
    # Sin esto, la cap `dashboard.read` cae al grupo 'Otros' y rompe el
    # ordenamiento esperado por rolesAclData.test.js.
    assert "dashboard: 'Análisis y crecimiento'" in src, (
        'BUG-117: `_GROUP_BY_DOMAIN` debe incluir `dashboard` para que la '
        'nueva cap aparezca en el grupo Análisis y crecimiento.'
    )


# ───── BUG-114 — NOT-APPLICABLE check (defensa anti-regresión) ───────────


def test_bug_114_services_mutations_remain_on_admin_router():
    """Si alguien movió alguna mutación de services de `tenant_admin_router` a
    un router con role más bajo, BUG-114 se vuelve VIGENTE. Este test defiende
    el statu-quo (los 4 mutadores siguen siendo admin+).
    """
    src = routes_aggregated_source()
    for path in (
        "@tenant_admin_router.post('/tenants/{tenant_id}/services'",
        "@tenant_admin_router.patch('/tenants/{tenant_id}/services/{service_id}'",
        "@tenant_admin_router.delete('/tenants/{tenant_id}/services/{service_id}'",
        "@tenant_admin_router.post('/tenants/{tenant_id}/services/reorder'",
    ):
        assert path in src, (
            f'BUG-114 regresión: la mutación `{path}` ya no está en '
            '`tenant_admin_router` — quedaría más abajo que `services.write`.'
        )
