"""Fix-group 21: BUG-123..BUG-127.

- BUG-123: VIGENTE. `FleetKpis` derivaba `active`/`trials`/`countries`
  de `items` (página actual, máx 100) pero mostraba los counts como
  si fueran totales. Cuando la flota supera 100 → undercount silencioso
  (≈ "X tenants activos" cuando en realidad hay X+). Fix: detectar
  `items.length < total` y degradar los KPIs sensibles a "—" con un
  footnote que aclare la limitación; cuando todo cabe en una página,
  los counts reflejan la flota completa y se muestran como antes.
- BUG-124: NOT-APPLICABLE. `resolveSafeHomeModule` (fix de BUG-011)
  ya descarta `platform-fleet` cuando el helper corre bajo `/t/{slug}/`,
  iterando `TENANT_NAV` y devolviendo el primer módulo tenant
  accesible. El platform_owner en support_mode aterriza en un módulo
  tenant válido (típicamente `tenant-setup`), nunca en un 404.
- BUG-125: NOT-APPLICABLE. `.claude/commands/continuar-ui-backlog.md`
  ya tiene "3.bis Actualización de docs (en el MISMO PR, antes del
  merge)" — las actualizaciones de UI_BACKLOG.md / DONE.md viajan en
  el PR del fix, no en commits posteriores.
- BUG-126: NOT-APPLICABLE. `TenantShellRoute` redirige
  `permissions.role === 'viewer'` a `/t/{slug}/read/{moduleId}` antes
  de montar el writable shell. Cubierto por test existente
  `router.test.jsx::"un viewer con deep-link al shell de escritura es
  redirigido a /read"`.
- BUG-127: NOT-APPLICABLE. `platform-fleet` SÍ está registrado en
  `adminModules` (modules.js línea 3), así que `useActiveModule` /
  `MODULE_REGISTRY['platform-fleet']` resuelven correctamente.
"""
from __future__ import annotations

from pathlib import Path


FLEET_KPIS = Path('admin-panel/src/features/platform/fleet-tenants/components/FleetKpis.jsx')
RESOLVE_SAFE_HOME = Path('admin-panel/src/app/resolveSafeHomeModule.js')
COMMAND_MD = Path('.claude/commands/continuar-ui-backlog.md')
ROUTER = Path('admin-panel/src/app/router.jsx')
MODULES = Path('admin-panel/src/app/modules.js')


# ───── BUG-123 — KPIs honestos con paginación ────────────────────────────


def test_bug_123_fleet_kpis_detects_partial_page():
    src = FLEET_KPIS.read_text()
    assert 'isPartial' in src, (
        'BUG-123: FleetKpis debe calcular `isPartial = items.length < total` '
        'para detectar cuándo el conteo de la página actual undercount el total real.'
    )
    assert 'items.length < total' in src, (
        'BUG-123: la heurística debe usar `items.length < total` (la página '
        'actual viene de useFleetTenants con limit 100).'
    )


def test_bug_123_fleet_kpis_degrades_active_count_when_partial():
    src = FLEET_KPIS.read_text()
    # Cuando isPartial, "Tenants activos" debe mostrar "—" (no un undercount).
    assert "value={isPartial ? '—' : String(active)}" in src, (
        'BUG-123: "Tenants activos" debe degradarse a "—" cuando '
        '`isPartial`, para no mostrar un undercount como si fuera el total.'
    )
    # Y el footnote debe mencionar la limitación.
    assert 'counts agregados pendientes de endpoint server-side' in src, (
        'BUG-123: el footnote debe aclarar que los counts agregados requieren '
        'un endpoint server-side (los counts del front son sobre la página actual).'
    )


def test_bug_123_fleet_kpis_degrades_countries_when_partial():
    src = FLEET_KPIS.read_text()
    assert "value={isPartial ? '—' : String(countries)}" in src, (
        'BUG-123: "Países cubiertos" debe degradarse a "—" cuando isPartial, '
        'sino subreporta los países (un país que solo tiene tenants en página '
        'siguiente no aparece).'
    )


# ───── BUG-124 — NOT-APPLICABLE (resolveSafeHomeModule cubre BUG-011) ────


def test_bug_124_resolve_safe_home_filters_platform_fleet_under_tenant_route():
    """Defensa anti-regresión del BUG-011, que cubre BUG-124. Sin este
    chequeo, el platform_owner navegando a `/t/{slug}/` con support_mode
    aterrizaría en `platform-fleet` (no existe bajo `/t/`) → 404.
    """
    src = RESOLVE_SAFE_HOME.read_text()
    assert 'navOrderSet.has(preferredHome)' in src, (
        'BUG-124/011: `resolveSafeHomeModule` debe filtrar `preferredHome` '
        'que NO esté en `flatNavOrder(role)` para que platform_owner en '
        'support_mode no aterrice en `platform-fleet` (404 bajo /t/).'
    )


# ───── BUG-125 — NOT-APPLICABLE (command file ya tiene 3.bis) ────────────


def test_bug_125_continuar_command_includes_docs_in_same_pr_step():
    src = COMMAND_MD.read_text()
    assert '## 3.bis' in src and 'en el MISMO PR' in src, (
        'BUG-125: `.claude/commands/continuar-ui-backlog.md` debe tener la '
        'sección "3.bis Actualización de docs (en el MISMO PR, antes del merge)" '
        'que evita que los commits de docs caigan en rama mergeada.'
    )


# ───── BUG-126 — NOT-APPLICABLE (TenantShellRoute redirige viewer) ───────


def test_bug_126_tenant_shell_route_redirects_viewer_to_read_subtree():
    src = ROUTER.read_text()
    # El TenantShellRoute debe redirigir viewer a /read/ antes de montar
    # el writable shell.
    shell_idx = src.find('function TenantShellRoute(')
    assert shell_idx > 0
    next_def = src.find('\nfunction ', shell_idx + 1)
    block = src[shell_idx:next_def]
    assert "permissions.role === 'viewer'" in block
    assert '/read/' in block, (
        'BUG-126: TenantShellRoute debe redirigir a `/t/{slug}/read/{moduleId}` '
        'cuando `permissions.role === \"viewer\"`, antes de montar el writable '
        'shell.'
    )


# ───── BUG-127 — NOT-APPLICABLE (platform-fleet SÍ está en modules) ──────


def test_bug_127_platform_fleet_is_registered_in_admin_modules():
    src = MODULES.read_text()
    assert "id: 'platform-fleet'," in src, (
        'BUG-127: `platform-fleet` debe estar registrado en `adminModules` '
        'para que `useActiveModule` / `MODULE_REGISTRY` puedan resolverlo '
        'cuando el platform_owner aterriza en `/platform`.'
    )
