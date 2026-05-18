"""Fix-group 33: BUG-185..BUG-190 — 7 P2 restantes de Codex Review.

- BUG-185 (P2 sobre BUG-085): `AuthProvider` inicializa `session=null`
  durante el `fetchAdminSession()` en flight. Los guards `NoTenantRoute`/
  `OnboardingRoute`/`PlatformRoute` trataban al user autenticado en mid-load
  como anónimo → redirect a `/` perdía el deep link. Fix: `RootLayout`
  chequea `useAuth().isLoading` y renderea `<LoadingScreen />` hasta que
  el status estabiliza.
- BUG-186 (P2 sobre BUG-084): el index nested de `path: 'read'` era un
  `<Navigate to={ROLE_HOME.viewer}>` estático; viewers sin la cap
  `analytics.tenant.read` aterrizaban en `viewer-summary` y veían
  AccessDenied. Fix: nuevo `ReadHomeRedirect` calcula `safeHome` con
  `resolveSafeHomeModule(permissions)` y cae a `NoModuleAccessScreen`.
- BUG-187: NOT-APPLICABLE — fix-group-29 follow-up commit ya flippeó
  el test stale de `test_auth_sessions_static.py`.
- BUG-188 (P2 sobre BUG-117): `modules.js` usa `dashboard.read` pero
  `moduleRegistry.js:68` seguía gating con `analytics.tenant.read`.
  Nav HIDE el item pero deep link directo renderizaba el Dashboard
  Owner para roles inferiores. Fix: alineado a `capability:
  'dashboard.read'` en ambos lugares.
- BUG-189 (P2 sobre BUG-083): rail colapsado tiene 48px internos pero
  `.brand` renderiza brandMark (40px) + gap (12px) + collapseToggle
  (32px) = 84px → clipping. Fix: hide `.brandMark` en collapsed, solo
  el toggle queda como control activo del row.
- BUG-190: NOT-APPLICABLE — fix-group-30 follow-up commit ya flippeó
  los tests de `test_backup_verifier_static.py` al patrón
  `"$CONTAINER_CMD" run -d`.
"""
from __future__ import annotations

from pathlib import Path


ROUTER = Path('admin-panel/src/app/router.jsx')
MODULE_REGISTRY = Path('admin-panel/src/app/moduleRegistry.js')
SIDEBAR_CSS = Path('admin-panel/src/app/shells/components/ShellSidebar.module.css')
AUTH_SESSIONS_TEST = Path('tests/test_auth_sessions_static.py')
BACKUP_VERIFIER_TEST = Path('tests/test_backup_verifier_static.py')


# ───── BUG-185 — RootLayout espera auth loading ──────────────────────────


def test_bug_185_root_layout_renders_loading_screen_while_auth_in_flight():
    src = ROUTER.read_text()
    fn_idx = src.find('function RootLayout() {')
    assert fn_idx > 0
    next_fn = src.find('\nfunction IndexRedirect', fn_idx)
    block = src[fn_idx:next_fn]
    # Debe consumir `isLoading` de useAuth().
    assert 'isLoading' in block, (
        'BUG-185: `RootLayout` debe consumir `isLoading` de `useAuth()` '
        'para distinguir auth-loading de anonymous.'
    )
    # Si `isLoading`, render `<LoadingScreen />` antes que cualquier guard.
    assert 'if (isLoading)' in block and '<LoadingScreen />' in block, (
        'BUG-185: `RootLayout` debe hacer `if (isLoading) return '
        '<LoadingScreen />` ANTES de pasar `session` a `TenantProvider` — '
        'sino los guards downstream tratan al user en mid-load como anónimo.'
    )


# ───── BUG-186 — ReadHomeRedirect en /t/:slug/read/ index ────────────────


def test_bug_186_read_index_uses_safe_home_redirect():
    src = ROUTER.read_text()
    # Existe el componente.
    assert 'function ReadHomeRedirect()' in src, (
        'BUG-186: debe existir un componente `ReadHomeRedirect` que use '
        '`resolveSafeHomeModule` (analog a `TenantHomeRedirect` para viewers).'
    )
    # Y se usa como index del path 'read'.
    read_idx = src.find("path: 'read'")
    assert read_idx > 0
    children_idx = src.find('children:', read_idx)
    next_route = src.find('\n          },', children_idx)
    children_block = src[children_idx:next_route]
    assert 'element: <ReadHomeRedirect />' in children_block, (
        "BUG-186: el `index: true` de `path: 'read'` debe usar "
        "`<ReadHomeRedirect />`, no `<Navigate to={ROLE_HOME.viewer}>` estático."
    )


# ───── BUG-187 — NOT-APPLICABLE (test ya flippeado) ──────────────────────


def test_bug_187_auth_sessions_test_uses_split_predicates():
    src = AUTH_SESSIONS_TEST.read_text()
    assert "'where user_id = $1' in source" in src, (
        'BUG-187: el test debe asertar los predicados por separado '
        '(`where user_id = $1` + `revoked_at is null`), no el match literal '
        'de la cadena contigua que el fix-group-29 split a multi-line.'
    )
    # La cadena legacy contigua NO debe estar en una assertion activa.
    assert "'where user_id = $1 and revoked_at is null'" not in src, (
        'BUG-187: la assertion legacy `where user_id = $1 and revoked_at '
        'is null` (single-line) debe haberse removido.'
    )


# ───── BUG-188 — moduleRegistry usa dashboard.read ───────────────────────


def test_bug_188_module_registry_dashboard_uses_dashboard_read():
    src = MODULE_REGISTRY.read_text()
    assert "dashboard: { Component: Dashboard, capability: 'dashboard.read' }" in src, (
        "BUG-188: `moduleRegistry['dashboard']` debe usar "
        "`capability: 'dashboard.read'`. Sin esto, deep link directo a "
        "`/t/<slug>/dashboard` renderiza Dashboard Owner para roles "
        "inferiores aunque el nav ya esté oculto."
    )
    # La capability vieja ya no debe estar asociada al dashboard module.
    dashboard_line_idx = src.find('dashboard: { Component: Dashboard')
    assert dashboard_line_idx > 0
    line_end = src.find('\n', dashboard_line_idx)
    dashboard_line = src[dashboard_line_idx:line_end]
    assert "'analytics.tenant.read'" not in dashboard_line, (
        "BUG-188: el row de `dashboard` ya NO debe gateear con "
        "`analytics.tenant.read` — esa cap aplica a otros módulos pero "
        "el Dashboard owner es Owner/Admin only."
    )


# ───── BUG-189 — sidebar colapsado oculta brandMark ──────────────────────


def test_bug_189_collapsed_sidebar_hides_brand_mark():
    src = SIDEBAR_CSS.read_text()
    # Debe existir una regla que oculta brandMark en colapsado.
    assert (
        ".sidebar[data-collapsed='true'] .brandMark {\n  display: none;\n}"
        in src
    ), (
        "BUG-189: en rail colapsado (48px internos), debe ocultarse "
        "`.brandMark` (40px) para que el `.collapseToggle` (32px) sea el "
        "único control del row y quepa sin clipping bajo `overflow: hidden`."
    )


# ───── BUG-190 — NOT-APPLICABLE (verifier tests ya flippeados) ───────────


def test_bug_190_verifier_tests_use_container_cmd_pattern():
    src = BACKUP_VERIFIER_TEST.read_text()
    assert '"$CONTAINER_CMD" run -d --rm' in src, (
        'BUG-190: los tests del verifier deben asertar el patrón '
        'parametrizado `"$CONTAINER_CMD" run -d --rm`, no el literal '
        '`docker run -d --rm` (que rompió al introducirse el podman fallback).'
    )
