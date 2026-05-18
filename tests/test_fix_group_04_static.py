"""Fix-group 04: BUG-038..BUG-042.

- BUG-038: selection bug en CampaignsTable — submit usaba `selectedId`
  pero el botón "Editar" funciona sobre cualquier fila → pisaba campaña.
- BUG-039: mismo bug en useSegmentsData.
- BUG-040: NOT-APPLICABLE — `SUPPORTED_COUNTRIES.values()` ya fix-eado
  con `default_locale(code) for code in SUPPORTED_COUNTRIES`.
- BUG-041: `audit.py` usaba `json.dumps()` sin `default=str` → UUIDs y
  datetimes en metadata reventaban TypeError. Afecta especialmente
  go-live audit que incluye snapshot del readiness con UUIDs.
- BUG-042: RESOLVED-IN-FOLLOWUP — BUG-007 ya agregó `roles: ['owner']` a
  la response de `create_own_tenant`.
"""
from __future__ import annotations

from pathlib import Path


CAMPAIGNS_HOOK = Path('admin-panel/src/features/manager/campaigns/hooks/useCampaignsData.js')
SEGMENTS_HOOK = Path('admin-panel/src/features/manager/segments/hooks/useSegmentsData.js')
AUDIT = Path('app/services/audit.py')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-038 — Campaigns editingId vs selectedId ───────────────────────


def test_bug_038_campaigns_uses_editing_id_in_update():
    """`submit()` debe llamar `updateCampaign` con `editingId`, no con
    `selectedId` (que puede apuntar a una fila distinta de la editada).
    """
    src = CAMPAIGNS_HOOK.read_text()
    assert 'updateCampaign(session, tenantId, editingId, payload)' in src, (
        'BUG-038: submit debe usar editingId. Si usa selectedId, editar '
        'una fila no seleccionada pisa la fila seleccionada.'
    )
    assert 'updateCampaign(session, tenantId, selectedId, payload)' not in src, (
        'BUG-038: regresión — `updateCampaign(..., selectedId, ...)` volvió '
        'a aparecer. Es exactamente el bug que reportó Codex.'
    )


def test_bug_038_campaigns_tracks_editing_id_state():
    """El hook debe tener un useState para `editingId` separado de selectedId."""
    src = CAMPAIGNS_HOOK.read_text()
    assert 'useState(null)' in src
    assert "const [editingId, setEditingId] = useState(null)" in src, (
        'BUG-038: hook debe declarar `editingId` como useState distinto de '
        '`selectedId`.'
    )
    assert 'setEditingId(campaign.id)' in src, (
        'BUG-038: `startEdit` debe setear `editingId = campaign.id` (no '
        'depender de selectedId).'
    )


# ───── BUG-039 — Segments mismo patrón ───────────────────────────────────


def test_bug_039_segments_uses_editing_id_in_update():
    src = SEGMENTS_HOOK.read_text()
    assert 'updateContactSegment(session, tenantId, editingId, payload)' in src, (
        'BUG-039: submit debe usar editingId.'
    )
    assert 'updateContactSegment(session, tenantId, selectedId, payload)' not in src, (
        'BUG-039: regresión — volvió `updateContactSegment(..., selectedId, ...)`.'
    )


def test_bug_039_segments_tracks_editing_id_state():
    src = SEGMENTS_HOOK.read_text()
    assert "const [editingId, setEditingId] = useState(null)" in src, (
        'BUG-039: hook debe declarar `editingId` como useState.'
    )
    assert 'setEditingId(segment.id)' in src, (
        'BUG-039: `startEdit` debe setear `editingId = segment.id`.'
    )


# ───── BUG-040 — NOT-APPLICABLE (SUPPORTED_COUNTRIES ya fix-eado) ───────


def test_bug_040_supported_countries_iterated_not_values():
    """`SUPPORTED_COUNTRIES` es tuple, no dict → `.values()` AttributeError.
    El fix debe iterar con `for code in SUPPORTED_COUNTRIES`.
    """
    src = ROUTES.read_text()
    # No queremos ver `.values()` directamente sobre SUPPORTED_COUNTRIES.
    assert 'SUPPORTED_COUNTRIES.values()' not in src, (
        'BUG-040: regresión — `SUPPORTED_COUNTRIES.values()` reaparece. '
        'Es tuple, no dict; itera con `for code in SUPPORTED_COUNTRIES`.'
    )
    # El fix existente usa default_locale(code).
    assert 'default_locale(code) for code in SUPPORTED_COUNTRIES' in src, (
        'BUG-040: el patron correcto `{default_locale(code) for code in '
        'SUPPORTED_COUNTRIES}` desapareció — PATCH /me/profile vuelve a 500.'
    )


# ───── BUG-041 — audit.py json.dumps con default=str ─────────────────────


def test_bug_041_audit_json_dumps_uses_default_str():
    """Tanto `audit()` como `audit_durably()` deben usar `default=str` en
    `json.dumps(metadata)`. Sin esto, cualquier metadata con UUID/datetime
    revienta con TypeError y el audit log no se persiste.
    """
    src = AUDIT.read_text()
    # Debe haber AL MENOS dos `json.dumps(metadata or {}, default=str)`
    # (uno en audit, otro en audit_durably). Conteo conservador.
    count_with_default = src.count('json.dumps(metadata or {}, default=str)')
    assert count_with_default >= 2, (
        f'BUG-041: esperaba al menos 2 `json.dumps(metadata or {{}}, '
        f'default=str)` (audit + audit_durably), encontré {count_with_default}.'
    )
    # No debe quedar ninguna `json.dumps(metadata or {})` sin default.
    assert 'json.dumps(metadata or {})' not in src, (
        'BUG-041: regresión — sigue habiendo `json.dumps(metadata or {{}})` '
        'sin `default=str`. UUIDs/datetimes en metadata vuelven a reventar.'
    )


# ───── BUG-042 — NOT-APPLICABLE (BUG-007 fix añadió `roles`) ────────────


def test_bug_042_create_own_tenant_returns_roles_array():
    """El response debe incluir `roles: ['owner']` además de `user_role`."""
    src = ROUTES.read_text()
    # Anchor a la función create_own_tenant.
    assert "response['roles'] = ['owner']" in src, (
        'BUG-042: regresión — `create_own_tenant` ya no incluye `roles: '
        "['owner']` en el response. El frontend (TenantProvider) lee "
        "`roles` o `role`; sin esto, owner nuevo cae en AccessDenied "
        "hasta refrescar (BUG-007 reabierto)."
    )
