"""Cover small gaps in app/services/consent.py."""
from __future__ import annotations



def test_record_get_none_returns_default():
    from app.services.consent import _record_get
    assert _record_get(None, 'key', 'fallback') == 'fallback'
    assert _record_get(None, 'key') is None


def test_record_get_dict_returns_value():
    from app.services.consent import _record_get
    assert _record_get({'k': 'v'}, 'k') == 'v'
    assert _record_get({'k': 'v'}, 'missing', 'default') == 'default'


def test_record_get_record_with_subscript():
    """Record-like that supports [key] subscript."""
    from app.services.consent import _record_get

    class _Rec:
        def __init__(self, d):
            self.d = d
        def __getitem__(self, key):
            return self.d[key]

    assert _record_get(_Rec({'k': 'v'}), 'k') == 'v'


def test_record_get_record_missing_returns_default():
    from app.services.consent import _record_get

    class _Rec:
        def __getitem__(self, key):
            raise KeyError(key)

    assert _record_get(_Rec(), 'missing', 'default') == 'default'


def test_parse_payload_string():
    from app.services.consent import _parse_payload
    assert _parse_payload('{"a": 1}') == {'a': 1}


def test_parse_payload_string_invalid():
    from app.services.consent import _parse_payload
    assert _parse_payload('not json') == {}


def test_parse_payload_dict_passthrough():
    from app.services.consent import _parse_payload
    d = {'k': 'v'}
    assert _parse_payload(d) is d


def test_parse_payload_other_returns_empty():
    from app.services.consent import _parse_payload
    assert _parse_payload(None) == {}
    assert _parse_payload(42) == {}


def test_interactive_id_extracts():
    from app.services.consent import _interactive_id
    msg = {'payload': {'interactive_id': 'consent:yes'}}
    assert _interactive_id(msg) == 'consent:yes'


def test_interactive_id_none_for_missing():
    from app.services.consent import _interactive_id
    assert _interactive_id({}) is None
    assert _interactive_id({'payload': {}}) is None


def test_is_consent_reply():
    from app.services.consent import is_consent_reply, CONSENT_BUTTON_YES, CONSENT_BUTTON_NO
    yes_msg = {'payload': {'interactive_id': CONSENT_BUTTON_YES}}
    no_msg = {'payload': {'interactive_id': CONSENT_BUTTON_NO}}
    other = {'payload': {'interactive_id': 'something_else'}}

    assert is_consent_reply(yes_msg) is True
    assert is_consent_reply(no_msg) is True
    assert is_consent_reply(other) is False


def test_build_consent_request_body_text():
    from app.services.consent import build_consent_request_body_text
    out = build_consent_request_body_text('Mi Negocio')
    assert 'Mi Negocio' in out


def test_build_consent_request_body_text_with_legal_url():
    from app.services.consent import build_consent_request_body_text
    out = build_consent_request_body_text('Mi Negocio', 'https://x.com/tos')
    assert 'x.com/tos' in out
