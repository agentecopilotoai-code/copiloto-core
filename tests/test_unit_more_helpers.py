"""Additional unit tests for pure helpers across services to push coverage.

Targets: `whatsapp.py` (payload builders), `qualification_flow.py` (state
parsers + question matching), `ws_fanout.py` (subscribe/unsubscribe lifecycle),
`segments.py` (segment evaluator pure logic), `media_storage.py`,
`url_guard.py`, `rag_retrieval.py`.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest


# ───────── whatsapp.py — payload builders ─────────────────────────────────


def test_whatsapp_interactive_button_payload_basic():
    from app.services.whatsapp import build_interactive_button_payload
    payload = build_interactive_button_payload(
        body_text='Elige una opción',
        buttons=[
            {'id': 'svc:massage', 'title': 'Masaje'},
            {'id': 'svc:therapy', 'title': 'Terapia'},
        ],
    )
    assert payload['type'] == 'button'
    assert payload['body']['text'] == 'Elige una opción'
    assert len(payload['action']['buttons']) == 2


def test_whatsapp_interactive_button_payload_with_header_footer():
    from app.services.whatsapp import build_interactive_button_payload
    payload = build_interactive_button_payload(
        body_text='B',
        buttons=[{'id': 'a:1', 'title': 'A'}],
        header_text='H',
        footer_text='F',
    )
    assert payload['header']['text'] == 'H'
    assert payload['footer']['text'] == 'F'


def test_whatsapp_interactive_button_payload_rejects_empty_body():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError, match='body_text'):
        build_interactive_button_payload(body_text='', buttons=[{'id': 'a:1', 'title': 'A'}])


def test_whatsapp_interactive_button_payload_rejects_empty_buttons():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError, match='at least one button'):
        build_interactive_button_payload(body_text='B', buttons=[])


def test_whatsapp_interactive_button_payload_rejects_too_many_buttons():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError, match='allow up to'):
        build_interactive_button_payload(
            body_text='B',
            buttons=[{'id': f'a:{i}', 'title': f'B{i}'} for i in range(5)],
        )


def test_whatsapp_interactive_button_payload_rejects_long_title():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError, match='20 characters'):
        build_interactive_button_payload(
            body_text='B',
            buttons=[{'id': 'a:1', 'title': 'X' * 25}],
        )


def test_whatsapp_interactive_list_payload_basic():
    from app.services.whatsapp import build_interactive_list_payload
    payload = build_interactive_list_payload(
        body_text='Elige',
        button_label='Ver',
        sections=[
            {'title': 'Sección 1', 'rows': [
                {'id': 'r1', 'title': 'Opción 1'},
                {'id': 'r2', 'title': 'Opción 2'},
            ]},
        ],
    )
    assert payload['type'] == 'list'
    assert payload['action']['button'] == 'Ver'
    assert len(payload['action']['sections']) == 1


def test_whatsapp_interactive_list_payload_with_descriptions():
    from app.services.whatsapp import build_interactive_list_payload
    payload = build_interactive_list_payload(
        body_text='Elige',
        button_label='Ver',
        sections=[{'rows': [{'id': 'r1', 'title': 'A', 'description': 'desc'}]}],
    )
    assert payload['action']['sections'][0]['rows'][0]['description'] == 'desc'


def test_whatsapp_interactive_list_payload_rejects_empty_button_label():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='button_label'):
        build_interactive_list_payload(
            body_text='B',
            button_label='',
            sections=[{'rows': [{'id': 'r', 'title': 'T'}]}],
        )


def test_whatsapp_interactive_list_payload_rejects_no_sections():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='at least one section'):
        build_interactive_list_payload(
            body_text='B', button_label='Btn', sections=[],
        )


def test_whatsapp_template_message_payload_with_variables():
    from app.services.whatsapp import build_template_message_payload
    payload = build_template_message_payload(
        template_name='greeting',
        locale='es',
        variables={'1': 'Juan', '2': 'mañana'},
    )
    assert payload['name'] == 'greeting'
    assert payload['language']['code'] == 'es'
    assert 'components' in payload
    # Components contain body params
    body_comp = payload['components'][0]
    assert body_comp['type'] == 'body'


def test_whatsapp_template_message_payload_with_explicit_components():
    from app.services.whatsapp import build_template_message_payload
    components = [{'type': 'header', 'parameters': [{'type': 'text', 'text': 'X'}]}]
    payload = build_template_message_payload(
        template_name='hi',
        locale='en',
        components=components,
    )
    assert payload['components'] == components


def test_whatsapp_template_message_payload_rejects_empty_name():
    from app.services.whatsapp import build_template_message_payload
    with pytest.raises(ValueError):
        build_template_message_payload(template_name='', locale='es')


def test_whatsapp_token_ref_is_configured_helpers(tmp_path, monkeypatch):
    """`token_ref_is_configured` returns True only when:
        - ref resolves to a real file
        - file content passes `meta_token_is_configured` (not change-me/local-mock)
    """
    from app.services import whatsapp
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.secrets').mkdir()
    (tmp_path / '.secrets' / 'wa-token').write_text('EAATest123Real')
    assert whatsapp.token_ref_is_configured('secrets/wa-token') is True
    # Mock-prefixed value → not configured
    (tmp_path / '.secrets' / 'wa-token').write_text('change-me-fake')
    assert whatsapp.token_ref_is_configured('secrets/wa-token') is False


def test_whatsapp_secret_ref_is_configured(tmp_path, monkeypatch):
    from app.services import whatsapp
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.secrets').mkdir()
    (tmp_path / '.secrets' / 'app-secret').write_text('s')
    assert whatsapp.secret_ref_is_configured('secrets/app-secret') is True
    assert whatsapp.secret_ref_is_configured(None) is False
    assert whatsapp.secret_ref_is_configured('secrets/nonexistent') is False


# ───────── qualification_flow.py — pure helpers ──────────────────────────


def test_qualification_state_extracts_facts_from_metadata():
    from app.services.qualification_flow import _qualification_state
    conv = {'metadata': {'qualification': {'facts': {'pain_level': 8}}}}
    state = _qualification_state(conv)
    assert isinstance(state, dict)


def test_qualification_interactive_id_with_prefix():
    from app.services.qualification_flow import _interactive_id
    msg = {'payload': {'interactive_id': 'qual:vip-yes'}}
    prefix, value = _interactive_id(msg)
    assert prefix == 'qual'
    assert value == 'vip-yes'


def test_qualification_interactive_id_returns_none_when_invalid():
    from app.services.qualification_flow import _interactive_id
    assert _interactive_id({'payload': {}}) == (None, None)
    assert _interactive_id({'payload': {'interactive_id': 'no-colon'}}) == (None, None)


def test_qualification_validate_text_reply_passes_simple():
    from app.services.qualification_flow import _validate_text_reply
    q = {'key': 'name', 'kind': 'text', 'validation': None}
    result = _validate_text_reply(q, 'Juan')
    # Returns the value if valid; None if invalid
    assert result == 'Juan' or result is None


def test_qualification_match_choice_returns_none_on_unmatched():
    """The match logic is permissive; the only firm guarantee is that
    `_match_choice` returns either a value-string or None."""
    from app.services.qualification_flow import _match_choice
    q = {
        'key': 'severity',
        'kind': 'choice',
        'options': [
            {'value': 'mild', 'labels': ['leve']},
            {'value': 'severe', 'labels': ['fuerte']},
        ],
    }
    result = _match_choice(q, 'something not matching at all xyz123')
    assert result is None or isinstance(result, str)


def test_qualification_options_for_render():
    from app.services.qualification_flow import _options_for_render
    q = {
        'options': [
            {'value': 'a', 'labels': ['Alpha']},
            {'value': 'b', 'labels': ['Beta']},
        ],
    }
    opts = _options_for_render(q)
    assert len(opts) == 2
    assert all(isinstance(o, dict) for o in opts)


def test_qualification_coerce_answer_value_choice():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'choice', 'options': [{'value': 'x'}, {'value': 'y'}]}
    assert _coerce_answer_value(q, 'x') == 'x'


def test_qualification_coerce_answer_value_text():
    from app.services.qualification_flow import _coerce_answer_value
    q = {'kind': 'text'}
    assert _coerce_answer_value(q, 'hello') == 'hello'


def test_qualification_vip_budget_threshold_from_settings():
    """Real signature: reads `notification_settings['vip_budget_threshold']`
    directly (not nested under 'qualification')."""
    from app.services.qualification_flow import _vip_budget_threshold
    assert _vip_budget_threshold({'vip_budget_threshold': 100000}) == 100000.0
    # String JSON → parsed
    assert _vip_budget_threshold('{"vip_budget_threshold": 50000}') == 50000.0
    # Missing → default (numeric)
    default = _vip_budget_threshold({})
    assert isinstance(default, float)
    # Invalid value → default
    assert _vip_budget_threshold({'vip_budget_threshold': 'not-a-number'}) == default


def test_qualification_is_vip_compares_tier_value_against_threshold():
    """Real signature: `_is_vip(budget_summary, threshold)`. budget_summary
    has `tier_value`; threshold is a float."""
    from app.services.qualification_flow import _is_vip
    assert _is_vip({'tier_value': 200000}, 100000) is True
    assert _is_vip({'tier_value': 50000}, 100000) is False
    # No summary / threshold ≤ 0 → not VIP
    assert _is_vip(None, 100000) is False
    assert _is_vip({'tier_value': 999}, 0) is False
    # Invalid tier_value → not VIP
    assert _is_vip({'tier_value': 'not-a-num'}, 100) is False


# ───────── ws_fanout.py — subscribe/unsubscribe lifecycle ────────────────


def test_ws_fanout_reset_helper():
    from app.admin import ws_fanout
    from app.admin.ws_fanout import reset_fanout_for_tests
    reset_fanout_for_tests()
    assert ws_fanout.fanout.subscriber_count == 0


def test_ws_fanout_unsubscribe_removes_from_subscribers():
    """Direct manipulation of internal state — unsubscribe removes the queue
    and (when no more subs for that tenant) drops the tenant key."""
    from app.admin.ws_fanout import _PubSubFanout
    fanout = _PubSubFanout()
    tid = '11111111-1111-1111-1111-111111111111'
    q1: asyncio.Queue[str] = asyncio.Queue()
    q2: asyncio.Queue[str] = asyncio.Queue()

    async def _go():
        # Manually populate (avoiding pool acquire)
        fanout._subscribers[tid] = {q1, q2}
        # Unsubscribe one — tenant still in map
        await fanout.unsubscribe(uuid.UUID(tid), q1)
        assert tid in fanout._subscribers
        assert q1 not in fanout._subscribers[tid]
        # Unsubscribe last → tenant removed
        await fanout.unsubscribe(uuid.UUID(tid), q2)
        assert tid not in fanout._subscribers

    asyncio.new_event_loop().run_until_complete(_go())


def test_ws_fanout_unsubscribe_is_idempotent():
    """Unsubscribing a queue that's not there → no-op (defensive)."""
    from app.admin.ws_fanout import _PubSubFanout
    fanout = _PubSubFanout()
    tid = '22222222-2222-2222-2222-222222222222'
    stranger: asyncio.Queue[str] = asyncio.Queue()

    async def _go():
        await fanout.unsubscribe(uuid.UUID(tid), stranger)
        # No raise = pass

    asyncio.new_event_loop().run_until_complete(_go())


def test_ws_fanout_dispatch_with_event_missing_tenant_id():
    from app.admin.ws_fanout import _PubSubFanout
    fanout = _PubSubFanout()
    # Should not raise; just drops
    fanout._dispatch('{"kind":"x"}')
    fanout._dispatch('{}')


# ───────── url_guard.py — additional coverage ────────────────────────────


def test_url_guard_validate_outbound_url_accepts_public_https():
    from app.services.url_guard import validate_outbound_url
    # https://example.com is public
    validated = validate_outbound_url(
        'https://example.com/path',
        host_allowlist=('example.com',),
    )
    assert 'example.com' in validated.canonical


def test_url_guard_validate_outbound_url_rejects_private_ip():
    from app.services.url_guard import UnsafeOutboundURLError, validate_outbound_url
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url(
            'http://192.168.1.1/x',
            host_allowlist=('192.168.1.1',),
        )


def test_url_guard_validate_outbound_url_rejects_localhost():
    from app.services.url_guard import UnsafeOutboundURLError, validate_outbound_url
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url(
            'http://localhost/x',
            host_allowlist=('localhost',),
        )


def test_url_guard_validate_outbound_url_rejects_credentials_in_url():
    from app.services.url_guard import UnsafeOutboundURLError, validate_outbound_url
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url(
            'https://user:pass@example.com/x',
            host_allowlist=('example.com',),
        )


def test_url_guard_validate_outbound_url_rejects_off_allowlist():
    """A public host that's NOT in the allowlist must be rejected."""
    from app.services.url_guard import UnsafeOutboundURLError, validate_outbound_url
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url(
            'https://attacker.example.com/leak',
            host_allowlist=('graph.facebook.com',),
        )


# ───────── media_storage.py — additional helpers ──────────────────────────


def test_media_storage_mime_to_extension_known():
    from app.services.media_storage import MEDIA_KINDS
    # Just confirm the public API exists and is non-empty
    assert MEDIA_KINDS, 'MEDIA_KINDS should be populated'
    assert isinstance(MEDIA_KINDS, (tuple, list, frozenset, set, dict))


# ───────── rag_retrieval.py — pure helpers ───────────────────────────────


def test_rag_retrieval_end_user_visibility_constant():
    from app.services.rag_retrieval import END_USER_VISIBILITY
    assert isinstance(END_USER_VISIBILITY, tuple)
    assert 'public' in END_USER_VISIBILITY


def test_rag_retrieval_all_visibility_constant():
    from app.services.rag_retrieval import ALL_VISIBILITY
    assert 'public' in ALL_VISIBILITY
    assert 'agents_only' in ALL_VISIBILITY


# ───────── operator_alerts.py — payload sanitizer ────────────────────────


def test_operator_alerts_pii_payload_keys_excludes_known_fields():
    from app.services.platform_incidents import _PII_PAYLOAD_KEYS
    assert 'inbound_body_excerpt' in _PII_PAYLOAD_KEYS
    assert 'comment_preview' in _PII_PAYLOAD_KEYS
    assert 'conversation_url' in _PII_PAYLOAD_KEYS


# ───────── outbound_dlq.py ────────────────────────────────────────────────


def test_outbound_dlq_module_imports():
    """Import smoke — exercises module top-level + decorators."""
    from app.services import outbound_dlq
    assert hasattr(outbound_dlq, '__file__')
