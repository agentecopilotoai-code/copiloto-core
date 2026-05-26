"""More tests for `app/services/metrics.py` — refresh helpers + recorders."""
from __future__ import annotations


# ═══ normalize_handoff_reason ═══════════════════════════════════════════


def test_normalize_handoff_reason_none():
    from app.services.metrics import normalize_handoff_reason
    assert normalize_handoff_reason(None) == 'unspecified'


def test_normalize_handoff_reason_empty():
    from app.services.metrics import normalize_handoff_reason
    assert normalize_handoff_reason('') == 'unspecified'
    assert normalize_handoff_reason('   ') == 'unspecified'


def test_normalize_handoff_reason_known():
    from app.services.metrics import normalize_handoff_reason
    assert normalize_handoff_reason('manual') == 'manual'
    assert normalize_handoff_reason('MANUAL') == 'manual'
    assert normalize_handoff_reason('risk keyword') == 'risk_keyword'


def test_normalize_handoff_reason_unknown_falls_to_other():
    from app.services.metrics import normalize_handoff_reason
    assert normalize_handoff_reason('weird thing') == 'other'


def test_normalize_handoff_reason_non_string():
    from app.services.metrics import normalize_handoff_reason
    assert normalize_handoff_reason(42) == 'other'


# ═══ _safe_tenant ═══════════════════════════════════════════════════════


def test_safe_tenant_none():
    from app.services.metrics import _safe_tenant
    assert _safe_tenant(None) == 'unknown'


def test_safe_tenant_uuid():
    from app.services.metrics import _safe_tenant
    from uuid import uuid4
    tid = uuid4()
    assert _safe_tenant(tid) == str(tid)


# ═══ record_message / record_appointment / record_llm_call etc. ═════════


def test_record_message_invalid_direction_returns_silently():
    from app.services.metrics import record_message
    # No raise; metric is just skipped
    record_message(tenant_id=None, direction='sideways', channel='inapp', status='sent')


def test_record_message_invalid_status_returns_silently():
    from app.services.metrics import record_message
    record_message(tenant_id=None, direction='inbound', channel='inapp', status='maybe')


def test_record_message_valid_increments():
    from app.services.metrics import record_message
    # Just ensure no raise
    record_message(tenant_id='t1', direction='inbound', channel='inapp', status='delivered')


def test_observe_response_latency_negative_skipped():
    from app.services.metrics import observe_response_latency
    observe_response_latency(tenant_id='t1', tier='template', seconds=-1.0)  # silent skip


def test_observe_response_latency_valid():
    from app.services.metrics import observe_response_latency
    observe_response_latency(tenant_id='t1', tier='template', seconds=0.5)


def test_record_llm_call_invalid_status_skipped():
    from app.services.metrics import record_llm_call
    record_llm_call(provider='openai', status='maybe')  # silent skip


def test_record_llm_call_valid():
    from app.services.metrics import record_llm_call
    record_llm_call(provider='openai', status='success')


def test_record_appointment_invalid_status_skipped():
    from app.services.metrics import record_appointment
    record_appointment(tenant_id='t1', status='weird_state')


def test_record_appointment_valid():
    from app.services.metrics import record_appointment
    record_appointment(tenant_id='t1', status='completed')


def test_record_handoff():
    from app.services.metrics import record_handoff
    record_handoff(tenant_id='t1', reason='manual')


def test_set_circuit_breaker_state_invalid_skipped():
    from app.services.metrics import set_circuit_breaker_state
    set_circuit_breaker_state(provider='ollama', state='exploded')  # not in CB_STATE_VALUES


def test_set_circuit_breaker_state_valid():
    from app.services.metrics import set_circuit_breaker_state
    for state in ('closed', 'half_open', 'open'):
        set_circuit_breaker_state(provider='ollama', state=state)


def test_set_worker_queue_depth_negative_skipped():
    from app.services.metrics import set_worker_queue_depth
    set_worker_queue_depth(worker='digest', depth=-1)


def test_set_worker_queue_depth_valid():
    from app.services.metrics import set_worker_queue_depth
    set_worker_queue_depth(worker='digest', depth=42)


def test_record_outbound_dlq_none_error_code():
    from app.services.metrics import record_outbound_dlq
    record_outbound_dlq(tenant_id='t1', error_code=None)


def test_record_outbound_dlq_with_code():
    from app.services.metrics import record_outbound_dlq
    record_outbound_dlq(tenant_id='t1', error_code='131026')


# ═══ _le_value ══════════════════════════════════════════════════════════


def test_le_value_inf_strings():
    from app.services.metrics import _le_value
    assert _le_value('+Inf') == float('inf')
    assert _le_value('Inf') == float('inf')


def test_le_value_numeric():
    from app.services.metrics import _le_value
    assert _le_value('0.5') == 0.5
    assert _le_value('10') == 10.0


def test_le_value_invalid_returns_inf():
    from app.services.metrics import _le_value
    assert _le_value('not-a-number') == float('inf')


# ═══ _histogram_quantile ═══════════════════════════════════════════════


def test_histogram_quantile_empty():
    from app.services.metrics import _histogram_quantile
    assert _histogram_quantile([], 0.5) is None


def test_histogram_quantile_no_observations():
    from app.services.metrics import _histogram_quantile
    buckets = [(0.5, 0), (1.0, 0), (float('inf'), 0)]
    assert _histogram_quantile(buckets, 0.5) is None


def test_histogram_quantile_basic():
    from app.services.metrics import _histogram_quantile
    # 10 observations: 5 in 0-0.5, 3 in 0.5-1.0, 2 in 1.0-inf
    buckets = [(0.5, 5), (1.0, 8), (float('inf'), 10)]
    # P50 (median) → rank 5 → exactly at 0.5
    out = _histogram_quantile(buckets, 0.5)
    assert out is not None
    assert 0.4 <= out <= 0.6


def test_histogram_quantile_at_inf_returns_prev_bound():
    from app.services.metrics import _histogram_quantile
    # Quantile in the +Inf bucket → returns the previous upper bound
    buckets = [(0.5, 5), (float('inf'), 10)]
    out = _histogram_quantile(buckets, 0.99)
    # Rank 9.9 falls in +Inf bucket → returns prev_bound = 0.5
    assert out == 0.5


# ═══ refresh_runtime_metrics ════════════════════════════════════════════


def test_refresh_runtime_metrics_safe_without_pool():
    """No raise even when no rate limiter or ws_fanout is initialized."""
    from app.services.metrics import refresh_runtime_metrics
    refresh_runtime_metrics()  # no raise


def test_refresh_runtime_metrics_with_rate_limiter():
    """When _active_rate_limiter is set, reads its size."""
    from app.services import metrics
    from app.services.rate_limit import RateLimiter

    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=60)
    metrics._set_active_rate_limiter(limiter)
    try:
        metrics.refresh_runtime_metrics()  # no raise
    finally:
        metrics._set_active_rate_limiter(None)


# ═══ render_latest + parse_ip_allowlist ═════════════════════════════════


def test_render_latest_returns_bytes():
    from app.services.metrics import render_latest
    body, content_type = render_latest()
    assert isinstance(body, bytes)
    assert isinstance(content_type, str)


def test_parse_ip_allowlist_none():
    from app.services.metrics import parse_ip_allowlist
    assert parse_ip_allowlist(None) == frozenset()


def test_parse_ip_allowlist_empty():
    from app.services.metrics import parse_ip_allowlist
    assert parse_ip_allowlist('') == frozenset()


def test_parse_ip_allowlist_comma_separated():
    from app.services.metrics import parse_ip_allowlist
    out = parse_ip_allowlist('1.1.1.1, 2.2.2.2 ,3.3.3.3')
    assert out == frozenset({'1.1.1.1', '2.2.2.2', '3.3.3.3'})


def test_parse_ip_allowlist_drops_blanks():
    from app.services.metrics import parse_ip_allowlist
    out = parse_ip_allowlist(', ,1.1.1.1,,')
    assert out == frozenset({'1.1.1.1'})


# ═══ collect_health_snapshot + evaluate_health_alerts ═══════════════════


def test_collect_health_snapshot_returns_dict():
    from app.services.metrics import collect_health_snapshot
    out = collect_health_snapshot()
    assert isinstance(out, dict)
    assert 'workers' in out
    assert 'circuit_breakers' in out


def test_evaluate_health_alerts_with_snapshot():
    """Use collect_health_snapshot to get a real shape, then evaluate."""
    from app.services.metrics import collect_health_snapshot, evaluate_health_alerts
    snapshot = collect_health_snapshot()
    out = evaluate_health_alerts(snapshot)
    assert isinstance(out, list)
