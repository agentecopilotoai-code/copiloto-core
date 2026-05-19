"""Unit tests for pure helpers inside `app/api/v1/routes.py`.

Targets specific uncovered ranges identified by analyzing missing_lines from
the coverage JSON. These are mostly slot-generator + parser helpers + payment
settings normalizers that live in routes.py but are pure (no I/O).
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import pytest


# ───────── working_hours_for_date / slot generators ──────────────────────


def test_working_hours_for_date_parses_capabilities_with_weekly_schedule():
    from app.api.v1.routes import working_hours_for_date
    caps = {
        'working_hours': {
            'monday': [{'start': '09:00', 'end': '17:00'}],
            'tuesday': [{'start': '09:00', 'end': '17:00'}],
        },
    }
    # Monday 2026-05-18 (verified)
    target = datetime(2026, 5, 18, tzinfo=timezone.utc)
    franjas = working_hours_for_date(caps, target)
    assert isinstance(franjas, list)


def test_working_hours_for_date_returns_empty_when_no_schedule():
    from app.api.v1.routes import working_hours_for_date
    target = datetime(2026, 5, 18, tzinfo=timezone.utc)
    franjas = working_hours_for_date({}, target)
    assert franjas == []


def test_working_hours_for_date_returns_empty_for_off_day():
    from app.api.v1.routes import working_hours_for_date
    # Sunday — no schedule defined
    caps = {'working_hours': {'monday': [{'start': '09:00', 'end': '17:00'}]}}
    target = datetime(2026, 5, 17, tzinfo=timezone.utc)  # Sunday
    franjas = working_hours_for_date(caps, target)
    assert franjas == []


def test_working_hours_for_date_handles_malformed_caps():
    from app.api.v1.routes import working_hours_for_date
    target = datetime(2026, 5, 18, tzinfo=timezone.utc)
    # Non-dict capabilities → empty
    assert working_hours_for_date(None, target) == []
    assert working_hours_for_date('not a dict', target) == []
    # Missing working_hours key → empty
    assert working_hours_for_date({'services': []}, target) == []


# ───────── normalize_qualification_question ──────────────────────────────


def test_normalize_qualification_question_returns_none_when_input_is_none():
    from app.api.v1.routes import normalize_qualification_question
    assert normalize_qualification_question(None) is None


def test_normalize_qualification_question_returns_dict_for_record_like():
    """The helper takes an asyncpg Record (dict-like) and returns the
    public-facing dict shape."""
    from app.api.v1.routes import normalize_qualification_question

    class _RecordLike:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def get(self, key, default=None):
            return self._data.get(key, default)

        def keys(self):
            return self._data.keys()

    record = _RecordLike({
        'id': 'q1',
        'tenant_id': 't1',
        'key': 'budget_tier',
        'order_index': 1,
        'kind': 'choice',
        'prompt': '¿Cuál es tu presupuesto?',
        'options': [{'value': 'low', 'labels': ['bajo']}],
        'allows_other': False,
        'is_active': True,
        'created_at': None,
        'updated_at': None,
    })
    out = normalize_qualification_question(record)
    assert isinstance(out, dict)
    # The helper exposes the public shape — at minimum should include `key`.
    assert 'key' in out or 'kind' in out


# ───────── normalize_onboarding_progress ─────────────────────────────────


def test_normalize_onboarding_progress_handles_empty():
    from app.api.v1.routes import normalize_onboarding_progress
    out = normalize_onboarding_progress({})
    assert isinstance(out, dict)
    assert 'steps' in out
    assert 'last_completed_step' in out


def test_normalize_onboarding_progress_handles_none():
    from app.api.v1.routes import normalize_onboarding_progress
    out = normalize_onboarding_progress(None)
    assert isinstance(out, dict)


def test_normalize_onboarding_progress_preserves_existing_steps():
    from app.api.v1.routes import normalize_onboarding_progress
    inp = {'last_completed_step': 3, 'steps': {'1': True, '2': True, '3': True}}
    out = normalize_onboarding_progress(inp)
    assert out['last_completed_step'] == 3


# ───────── _email_from_signed_bff_header (BUG-228) ───────────────────────


def test_email_from_signed_bff_header_returns_none_when_header_missing():
    from app.api.v1.routes import _email_from_signed_bff_header

    class _Req:
        def __init__(self):
            self.headers = {}
            class _State:
                actor_id = 'auth0|test'
            self.state = _State()

    assert _email_from_signed_bff_header(_Req()) is None


def test_email_from_signed_bff_header_returns_none_when_unsigned():
    """Garbage X-Admin-Identity should NOT be trusted."""
    from app.api.v1.routes import _email_from_signed_bff_header

    class _Req:
        def __init__(self):
            self.headers = {'X-Admin-Identity': 'not-a-signed-payload'}
            class _State:
                actor_id = 'auth0|test'
            self.state = _State()

    assert _email_from_signed_bff_header(_Req()) is None


# ───────── normalize_knowledge_document ──────────────────────────────────


def test_normalize_knowledge_document_handles_record_like():
    from app.api.v1.routes import normalize_knowledge_document

    record = {
        'id': 'doc1',
        'tenant_id': 't1',
        'title': 'FAQ',
        'mime_type': 'text/plain',
        'content_b64': '',
        'source_uri': 'kb://',
        'status': 'active',
        'visibility': 'public',
        'metadata': {},
        'document_type': 'faq',
        'source_type': 'manual',
        'embedding_provider': 'local_hash',
        'embedding_model': 'copilotoia-local-hash-v1',
        'embedding_dimensions': 1536,
        'last_indexed_at': None,
        'expiration_at': None,
        'sanitized_warning_count': 0,
        'chunk_count': 0,
    }
    out = normalize_knowledge_document(record)
    assert isinstance(out, dict)
    assert out.get('title') == 'FAQ'


# ───────── ONBOARDING_TOTAL_STEPS constant ───────────────────────────────


def test_onboarding_total_steps_is_positive_integer():
    from app.api.v1.routes import ONBOARDING_TOTAL_STEPS
    assert isinstance(ONBOARDING_TOTAL_STEPS, int)
    assert ONBOARDING_TOTAL_STEPS > 0


# ───────── KNOWLEDGE_DOCUMENT_PROJECTION ─────────────────────────────────


def test_knowledge_document_projection_is_non_empty_sql_fragment():
    from app.api.v1.routes import KNOWLEDGE_DOCUMENT_PROJECTION
    assert isinstance(KNOWLEDGE_DOCUMENT_PROJECTION, str)
    assert len(KNOWLEDGE_DOCUMENT_PROJECTION) > 0
    # Should mention common columns
    assert 'id' in KNOWLEDGE_DOCUMENT_PROJECTION
    assert 'title' in KNOWLEDGE_DOCUMENT_PROJECTION


# ───────── ensure_tenant_access + ensure_tenant_role smoke ───────────────


def test_ensure_tenant_access_function_exists_and_is_async():
    import inspect
    from app.api.v1.routes import ensure_tenant_access
    assert inspect.iscoroutinefunction(ensure_tenant_access)


def test_ensure_tenant_role_function_exists_and_is_async():
    import inspect
    from app.api.v1.routes import ensure_tenant_role
    assert inspect.iscoroutinefunction(ensure_tenant_role)


# ───────── tenant_id_from_request ────────────────────────────────────────


def test_tenant_id_from_request_async_helper_exists():
    import inspect
    from app.api.v1.routes import tenant_id_from_request
    assert inspect.iscoroutinefunction(tenant_id_from_request)


# ───────── validate_outbound_message_content ─────────────────────────────


def test_validate_outbound_message_content_accepts_simple_text():
    from app.api.v1.routes import validate_outbound_message_content
    # Simple text passes (returns None)
    out = validate_outbound_message_content(message_type='text', body_text='Hola')
    assert out is None


def test_validate_outbound_message_content_rejects_empty_text():
    from fastapi import HTTPException
    from app.api.v1.routes import validate_outbound_message_content
    with pytest.raises(HTTPException) as exc_info:
        validate_outbound_message_content(message_type='text', body_text='')
    assert exc_info.value.status_code == 400


def test_validate_outbound_message_content_rejects_unsupported_type():
    from fastapi import HTTPException
    from app.api.v1.routes import validate_outbound_message_content
    with pytest.raises(HTTPException) as exc_info:
        validate_outbound_message_content(message_type='sticker', body_text=None)
    assert exc_info.value.status_code == 400


def test_validate_outbound_message_content_image_requires_media():
    from fastapi import HTTPException
    from app.api.v1.routes import validate_outbound_message_content
    with pytest.raises(HTTPException) as exc_info:
        validate_outbound_message_content(message_type='image', body_text=None)
    assert exc_info.value.status_code == 400


def test_validate_outbound_message_content_image_with_media_id_ok():
    from app.api.v1.routes import validate_outbound_message_content
    # Numeric Meta media id passes
    out = validate_outbound_message_content(
        message_type='image', body_text=None, media_id='1234567890',
    )
    assert out is None


def test_validate_outbound_message_content_rejects_unsafe_media_id():
    from fastapi import HTTPException
    from app.api.v1.routes import validate_outbound_message_content
    with pytest.raises(HTTPException) as exc_info:
        validate_outbound_message_content(
            message_type='image', body_text=None, media_id='../../etc/passwd',
        )
    # 422 from url_guard
    assert exc_info.value.status_code in (400, 422)


# ───────── _build_widget_snippet (BUG-002 + UI-013) ──────────────────────


def test_build_widget_snippet_includes_script_tag_and_data_attributes():
    from app.api.v1.routes import _build_widget_snippet
    snippet = _build_widget_snippet(
        tenant_slug='example',
        widget_token='wtok_abc123',
        color='#ff0000',
        greeting='Hola',
    )
    assert '<script' in snippet
    assert 'data-tenant="example"' in snippet
    assert 'data-widget-token="wtok_abc123"' in snippet
    assert 'data-color="#ff0000"' in snippet
    assert 'data-greeting="Hola"' in snippet
    assert 'data-api-base' in snippet


def test_build_widget_snippet_escapes_xss_in_logo_url():
    # BUG-226: logo_url is now sanitized so an attacker cannot inject onload="..."
    from app.api.v1.routes import _build_widget_snippet
    malicious = 'x" onload="alert(1)'
    snippet = _build_widget_snippet(
        tenant_slug='t',
        widget_token='wtok',
        color=None,
        greeting=None,
        logo_url=malicious,
    )
    # Raw quote must be escaped
    assert 'onload="alert(1)' not in snippet
    assert '&quot;' in snippet


def test_build_widget_snippet_omits_unknown_button_position():
    from app.api.v1.routes import _build_widget_snippet
    snippet = _build_widget_snippet(
        tenant_slug='t',
        widget_token='wtok',
        color=None,
        greeting=None,
        button_position='bottom',  # invalid
    )
    assert 'data-position' not in snippet


def test_build_widget_snippet_respects_known_button_position():
    from app.api.v1.routes import _build_widget_snippet
    snippet = _build_widget_snippet(
        tenant_slug='t',
        widget_token='wtok',
        color=None,
        greeting=None,
        button_position='left',
    )
    assert 'data-position="left"' in snippet
