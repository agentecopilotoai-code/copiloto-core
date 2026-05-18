"""Fix-group 29 (FINAL): BUG-163..BUG-168.

- BUG-163: NOT-APPLICABLE. La rama auto-select de `booking_flow` cuando
  queda exactamente 1 servicio tras qualification SÍ llama
  `_present_packages` antes de `_present_branches` (líneas 696-721).
  El comentario explícito en 680-685 lo documenta.
- BUG-164: NOT-APPLICABLE. `_list_active_services` NO aplica SQL
  `limit` — pulls el catálogo completo (`order by sort_order asc, name asc`,
  sin `limit`). El cap visual de 10 se aplica DESPUÉS del filtro de
  qualification en `_present_services`. El comment en 107-109 lo
  documenta.
- BUG-165: NOT-APPLICABLE. La rama de urgency completion SUSTITUYE
  `policy.handoff_message` por `URGENCY_WAIT_MESSAGE` (línea 761),
  no las suma. El comment en 758-761 lo documenta.
- BUG-166: NOT-APPLICABLE. El CTE de reply rates no depende de
  `inbound.campaign_id` — usa stitching por conversation+time
  (comment líneas 13205-13209) que funciona porque el WhatsApp
  webhook no carga campaign_id en los inbound.
- BUG-167: RESOLVED-DUPLICATE-BUG-136. Mismo issue, ya cerrado.
- BUG-168: VIGENTE. `GET /me/sessions` solo filtraba
  `revoked_at is null`, sin filtro por `last_seen_at`. Sesiones
  cuyos JWT ya expiraron pero nadie revocó aparecían como activas.
  Fix: nueva constante `AUTH_SESSION_ACTIVE_HOURS = 24` + filtro
  `last_seen_at >= now() - 24h` en el SELECT.
"""
from __future__ import annotations

from pathlib import Path


BOOKING_FLOW = Path('app/services/booking_flow.py')
RAG_ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-163 — auto-select usa _present_packages ───────────────────────


def test_bug_163_booking_flow_auto_select_calls_present_packages():
    src = BOOKING_FLOW.read_text()
    # En la rama `if len(eligible) == 1:`, debe llamarse `_present_packages`.
    auto_idx = src.find('if len(eligible) == 1:')
    assert auto_idx > 0
    next_block = src.find('if next_state is None:\n            next_state = await _present_branches', auto_idx)
    assert next_block > 0
    block = src[auto_idx:next_block]
    assert '_present_packages(' in block, (
        "BUG-163: la rama auto-select de booking_flow (1 servicio elegible) "
        "debe llamar `_present_packages` antes de `_present_branches` para no "
        "perder un paquete pagado."
    )


# ───── BUG-164 — _list_active_services sin SQL limit ─────────────────────


def test_bug_164_list_active_services_pulls_full_catalogue():
    src = BOOKING_FLOW.read_text()
    fn_idx = src.find('async def _list_active_services(')
    assert fn_idx > 0
    next_def = src.find('\n\ndef ', fn_idx)
    block = src[fn_idx:next_def]
    # El SQL NO debe tener `limit` al final.
    assert 'limit ' not in block.lower() or 'LIMIT ' not in block, (
        "BUG-164: `_list_active_services` no debe aplicar SQL `limit` — el "
        "filtro de qualification debe ver TODO el catálogo. El cap visual "
        "(10) se aplica después en `_present_services`."
    )
    # Y debe ordenar por sort_order + name (señal de que es el full pull).
    assert 'order by sort_order asc, name asc' in block, (
        "BUG-164: el SELECT debe ordenar por `sort_order asc, name asc`."
    )


# ───── BUG-165 — urgency completion sustituye handoff_message ────────────


def test_bug_165_urgency_completion_overrides_handoff_message():
    src = RAG_ORCHESTRATOR.read_text()
    # Buscar el override: `triage_policy = {**policy, 'handoff_message': URGENCY_WAIT_MESSAGE}`.
    assert "triage_policy = {**policy, 'handoff_message': URGENCY_WAIT_MESSAGE}" in src, (
        "BUG-165: la rama de urgency completion debe SUSTITUIR `handoff_message` "
        "con `URGENCY_WAIT_MESSAGE` (spread con override), no concatenar — "
        "sino el cliente recibe dos mensajes (URGENCY_WAIT + handoff genérico)."
    )


# ───── BUG-166 — CTE reply rates stitcha por conversation+time ──────────


def test_bug_166_campaign_reply_rates_use_conversation_time_join():
    src = ROUTES.read_text()
    # Buscar el CTE `replies as (` cerca de la query de campaigns. Usamos
    # `group by om.campaign_id` como cierre del CTE (más estable que `),`
    # porque dentro del CTE hay `)::interval`).
    cte_idx = src.find('replies as (\n          -- A "reply"')
    assert cte_idx > 0
    end = src.find('group by om.campaign_id', cte_idx)
    assert end > 0
    block = src[cte_idx:end]
    # Debe stitchar por conversation_id + tiempo (no por campaign_id en el inbound).
    assert "im.conversation_id = om.conversation_id" in block, (
        "BUG-166: el CTE de reply rates debe joinear `im.conversation_id "
        "= om.conversation_id` (stitching por conversación) porque el webhook "
        "no setea `campaign_id` en los inbound."
    )
    # Y no debe filtrar `im.campaign_id is not null` (sería siempre 0).
    assert 'im.campaign_id' not in block, (
        "BUG-166: el CTE NO debe condicionarse por `im.campaign_id` (que el "
        "webhook nunca setea); usar `om.campaign_id` del outbound."
    )


# ───── BUG-168 — /me/sessions filtra por freshness ──────────────────────


def test_bug_168_auth_session_active_hours_constant_exists():
    src = ROUTES.read_text()
    assert 'AUTH_SESSION_ACTIVE_HOURS = 24' in src, (
        "BUG-168: debe existir la constante `AUTH_SESSION_ACTIVE_HOURS` "
        "(default 24h) que define la ventana de freshness para considerar "
        "una sesión viva."
    )


def test_bug_168_list_my_sessions_filters_stale_rows():
    src = ROUTES.read_text()
    ep_idx = src.find("@me_router.get('/me/sessions')")
    assert ep_idx > 0
    next_ep = src.find('\n@me_router.', ep_idx + 10)
    block = src[ep_idx:next_ep]
    # La query debe filtrar last_seen_at >= now() - AUTH_SESSION_ACTIVE_HOURS.
    assert "last_seen_at >= now() - ($2 || ' hours')::interval" in block, (
        "BUG-168: `GET /me/sessions` debe filtrar "
        "`last_seen_at >= now() - (AUTH_SESSION_ACTIVE_HOURS || ' hours')::interval` "
        "para esconder sesiones cuyo JWT ya expiró."
    )
    assert 'AUTH_SESSION_ACTIVE_HOURS' in block, (
        "BUG-168: la query debe pasar `AUTH_SESSION_ACTIVE_HOURS` como parámetro."
    )
