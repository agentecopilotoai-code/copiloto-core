"""Fix-group 43: Codex Security MEDIUM — frontend XSS / input validation.

- **BUG-224** (MEDIUM, `agentPerformanceData.js`): `buildAgentsCsv` solo
  doubleaba `"` — no escapaba `=/+/-/@/tab/CR` que Excel/LibreOffice/Sheets
  interpretan como formula trigger. Agent malicioso → exfiltration via
  `=WEBSERVICE(...)` cuando admin exporta.
- **BUG-225** (MEDIUM, `viewerAppointmentsData.js`): `csvCell` solo
  escapaba `[",;\\r\\n]`. Mismo problema con formula triggers.
- **BUG-226** (MEDIUM, `app/api/v1/routes.py:_build_widget_snippet`):
  `data-logo="{logo_url}"` insertaba el valor RAW. Tenant admin podía
  persistir `logo_url=x" onload=...`; visitors del site del tenant
  ejecutaban JS atacante.
- **BUG-227** (MEDIUM, `BranchFormDrawer.jsx`): `<a href={form.maps_url}>`
  sin scheme allowlist → admin malicioso persistía `maps_url=javascript:...`,
  otro admin clickaba "Abrir" y el browser ejecutaba JS en el origin
  del admin panel.
"""
from __future__ import annotations

from pathlib import Path


AGENT_CSV = Path('admin-panel/src/features/owner-admin/analytics/agentPerformanceData.js')
APPT_CSV = Path('admin-panel/src/features/viewer/appointments/viewerAppointmentsData.js')
ROUTES = Path('app/api/v1/routes.py')
BRANCH_FORM = Path('admin-panel/src/features/owner-admin/branches/components/BranchFormDrawer.jsx')


def test_bug_224_agent_csv_escapes_formula_triggers():
    src = AGENT_CSV.read_text()
    assert "'=+-@\\t\\r'.includes(raw[0])" in src, (
        'BUG-224: `buildAgentsCsv` debe testear formula trigger chars '
        "(`=+-@\\t\\r`) y prefijar con `'`."
    )
    assert "safeCell" in src, (
        'BUG-224: debe existir helper `safeCell` que aplique el prefix.'
    )


def test_bug_225_appointments_csv_escapes_formula_triggers():
    src = APPT_CSV.read_text()
    assert "'=+-@\\t\\r'.includes(str[0])" in src, (
        "BUG-225: csvCell debe testear formula trigger chars en el primer "
        "char del string y prefijar con apostrofe."
    )


def test_bug_226_widget_snippet_escapes_logo_url():
    src = ROUTES.read_text()
    fn_idx = src.find('def _build_widget_snippet(')
    next_def = src.find('\n@tenant_admin_router', fn_idx)
    block = src[fn_idx:next_def]
    assert "logo_url.replace('\"', '&quot;')" in block, (
        'BUG-226: `_build_widget_snippet` debe escapar `"` del `logo_url` a '
        '`&quot;` (igual que el greeting/welcome_copy adyacentes).'
    )


def test_bug_227_branch_form_drawer_validates_maps_href_scheme():
    src = BRANCH_FORM.read_text()
    assert 'function isSafeMapsHref(' in src, (
        'BUG-227: debe existir el helper `isSafeMapsHref` que valide el '
        'scheme del maps_url antes de pasar al `<a href={...}>`.'
    )
    assert "trimmed.startsWith('http://') || trimmed.startsWith('https://')" in src, (
        'BUG-227: el helper debe aceptar solo `http://` y `https://` (+ '
        '`maps://` opcionalmente) — rechazar `javascript:` y otros schemes.'
    )
    assert 'isSafeMapsHref(form.maps_url)' in src, (
        'BUG-227: el `<a href>` del maps debe estar gateado por `isSafeMapsHref`.'
    )
