"""Pure-helper tests for `app/services/rag_orchestrator.py`.

These tests cover the small synchronous helpers that don't need the
asyncpg conn, the LLM stack, or the conversational orchestrator. The
DB-driven flows are exercised by test_unit_rag_orchestrator_db.py.
"""
from __future__ import annotations

from types import SimpleNamespace



# ───────── _is_cloud_llm_configured ──────────────────────────────────────


def test_is_cloud_llm_configured_both_set():
    from app.services.rag_orchestrator import _is_cloud_llm_configured
    s = SimpleNamespace(cloud_llm_provider='claude', cloud_llm_api_key='sk-test')
    assert _is_cloud_llm_configured(s) is True


def test_is_cloud_llm_configured_missing_provider():
    from app.services.rag_orchestrator import _is_cloud_llm_configured
    s = SimpleNamespace(cloud_llm_provider=None, cloud_llm_api_key='sk')
    assert _is_cloud_llm_configured(s) is False


def test_is_cloud_llm_configured_missing_key():
    from app.services.rag_orchestrator import _is_cloud_llm_configured
    s = SimpleNamespace(cloud_llm_provider='claude', cloud_llm_api_key=None)
    assert _is_cloud_llm_configured(s) is False


def test_is_cloud_llm_configured_both_empty():
    from app.services.rag_orchestrator import _is_cloud_llm_configured
    s = SimpleNamespace(cloud_llm_provider='', cloud_llm_api_key='')
    assert _is_cloud_llm_configured(s) is False


# ───────── _pending_recall_service_id ────────────────────────────────────


def test_pending_recall_service_id_returns_value():
    from app.services.rag_orchestrator import _pending_recall_service_id
    conv = {'metadata': {'pending_recall': {'service_id': 'svc-1'}}}
    assert _pending_recall_service_id(conv) == 'svc-1'


def test_pending_recall_service_id_from_json_string_metadata():
    from app.services.rag_orchestrator import _pending_recall_service_id
    conv = {'metadata': '{"pending_recall": {"service_id": "svc-2"}}'}
    assert _pending_recall_service_id(conv) == 'svc-2'


def test_pending_recall_service_id_none_for_missing():
    from app.services.rag_orchestrator import _pending_recall_service_id
    assert _pending_recall_service_id({}) is None
    assert _pending_recall_service_id({'metadata': {}}) is None
    assert _pending_recall_service_id({'metadata': {'pending_recall': {}}}) is None
    assert _pending_recall_service_id({'metadata': None}) is None


def test_pending_recall_service_id_invalid_json():
    from app.services.rag_orchestrator import _pending_recall_service_id
    assert _pending_recall_service_id({'metadata': 'broken json'}) is None


def test_pending_recall_service_id_non_dict_conversation():
    from app.services.rag_orchestrator import _pending_recall_service_id
    assert _pending_recall_service_id('not a dict') is None


def test_pending_recall_service_id_non_string_service_id():
    from app.services.rag_orchestrator import _pending_recall_service_id
    conv = {'metadata': {'pending_recall': {'service_id': 123}}}
    assert _pending_recall_service_id(conv) is None
    conv = {'metadata': {'pending_recall': {'service_id': ''}}}
    assert _pending_recall_service_id(conv) is None


# ───────── _parse_escalation_policy ──────────────────────────────────────


def test_parse_escalation_policy_dict_passthrough():
    from app.services.rag_orchestrator import _parse_escalation_policy
    p = {'rules': [1, 2, 3]}
    assert _parse_escalation_policy(p) is p


def test_parse_escalation_policy_json_string_decodes():
    from app.services.rag_orchestrator import _parse_escalation_policy
    assert _parse_escalation_policy('{"k": "v"}') == {'k': 'v'}


def test_parse_escalation_policy_invalid_returns_empty():
    from app.services.rag_orchestrator import _parse_escalation_policy
    assert _parse_escalation_policy('not json') == {}
    assert _parse_escalation_policy(None) == {}
    assert _parse_escalation_policy(42) == {}


# ───────── _current_datetime_label ───────────────────────────────────────


def test_current_datetime_label_valid_timezone():
    from app.services.rag_orchestrator import _current_datetime_label
    label, tz_name = _current_datetime_label('America/Bogota')
    assert tz_name == 'America/Bogota'
    # label contains a Spanish weekday + date + time
    assert any(day in label for day in
               ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'))


def test_current_datetime_label_falls_back_on_invalid():
    from app.services.rag_orchestrator import _current_datetime_label
    label, tz_name = _current_datetime_label('Not/A/Real/Timezone')
    assert tz_name == 'America/Bogota'
    assert isinstance(label, str)


def test_current_datetime_label_falls_back_on_trailing_slash():
    """SEC-010: legacy `'America/Bogota/'` shouldn't crash the handler."""
    from app.services.rag_orchestrator import _current_datetime_label
    _, tz_name = _current_datetime_label('America/Bogota/')
    assert tz_name == 'America/Bogota'


def test_current_datetime_label_falls_back_on_none():
    from app.services.rag_orchestrator import _current_datetime_label
    _, tz_name = _current_datetime_label(None)
    assert tz_name == 'America/Bogota'


def test_current_datetime_label_falls_back_on_empty():
    from app.services.rag_orchestrator import _current_datetime_label
    _, tz_name = _current_datetime_label('')
    assert tz_name == 'America/Bogota'


def test_current_datetime_label_falls_back_on_int():
    from app.services.rag_orchestrator import _current_datetime_label
    _, tz_name = _current_datetime_label(123)
    assert tz_name == 'America/Bogota'


# ───────── _tier_from_result ─────────────────────────────────────────────


def test_tier_from_result_unknown_for_non_dict():
    from app.services.rag_orchestrator import _tier_from_result
    assert _tier_from_result('not a dict') == 'unknown'
    assert _tier_from_result(None) == 'unknown'
    assert _tier_from_result([]) == 'unknown'


def test_tier_from_result_cloud_llm_wins():
    from app.services.rag_orchestrator import _tier_from_result
    result = {'cloud_llm_used': True, 'llm_used': True, 'action': 'bot_reply'}
    assert _tier_from_result(result) == 'cloud_llm'


def test_tier_from_result_local_llm_when_cloud_not_used():
    from app.services.rag_orchestrator import _tier_from_result
    result = {'cloud_llm_used': False, 'llm_used': True, 'action': 'bot_reply'}
    assert _tier_from_result(result) == 'local_llm'


def test_tier_from_result_bot_reply_action_maps_to_template():
    from app.services.rag_orchestrator import _tier_from_result
    result = {'action': 'bot_reply'}
    assert _tier_from_result(result) == 'template'


def test_tier_from_result_handoff_action():
    from app.services.rag_orchestrator import _tier_from_result
    result = {'action': 'handoff'}
    assert _tier_from_result(result) == 'handoff'


def test_tier_from_result_unknown_action_passes_through():
    from app.services.rag_orchestrator import _tier_from_result
    assert _tier_from_result({'action': 'skipped'}) == 'skipped'
    # When no action is set, returns 'unknown'
    assert _tier_from_result({}) == 'unknown'


# ───────── _tenant_allows_cloud_llm ──────────────────────────────────────


def test_tenant_allows_cloud_llm_explicit_false_allows():
    from app.services.rag_orchestrator import _tenant_allows_cloud_llm
    assert _tenant_allows_cloud_llm(False) is True


def test_tenant_allows_cloud_llm_default_none_blocks():
    """AUDIT-49: fail-closed — None and True both BLOCK cloud."""
    from app.services.rag_orchestrator import _tenant_allows_cloud_llm
    assert _tenant_allows_cloud_llm(None) is False
    assert _tenant_allows_cloud_llm(True) is False
