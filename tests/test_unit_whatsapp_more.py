"""Extra tests for app/services/whatsapp.py — push interactive + media coverage."""
from __future__ import annotations

import asyncio

import httpx
import pytest


# ─── parse_interactive_reply ──────────────────────────────────────────────


def test_parse_interactive_reply_non_dict():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply('not a dict') is None


def test_parse_interactive_reply_no_interactive_key():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply({'other': 'value'}) is None


def test_parse_interactive_reply_unknown_type():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply({'interactive': {'type': 'unknown'}}) is None


def test_parse_interactive_reply_button_no_dict():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply({'interactive': {'type': 'button_reply', 'button_reply': 'oops'}}) is None


def test_parse_interactive_reply_missing_id_or_title():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply({'interactive': {'type': 'button_reply',
                                                     'button_reply': {'id': 123, 'title': 'X'}}}) is None
    assert parse_interactive_reply({'interactive': {'type': 'button_reply',
                                                     'button_reply': {'id': 'x', 'title': 7}}}) is None


def test_parse_interactive_reply_button_ok():
    from app.services.whatsapp import parse_interactive_reply
    out = parse_interactive_reply({
        'interactive': {'type': 'button_reply', 'button_reply': {'id': 'BTN', 'title': 'Hi'}},
    })
    assert out['interactive_id'] == 'BTN'
    assert out['interactive_type'] == 'button_reply'


def test_parse_interactive_reply_list_with_description():
    from app.services.whatsapp import parse_interactive_reply
    out = parse_interactive_reply({
        'interactive': {'type': 'list_reply', 'list_reply': {
            'id': 'ID1', 'title': 'Hi', 'description': 'Desc',
        }},
    })
    assert out['interactive_description'] == 'Desc'


# ─── build_interactive_list_payload edge cases ────────────────────────────


def test_build_interactive_list_payload_requires_body():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='body_text'):
        build_interactive_list_payload('', 'go', [{'rows': [{'id': '1', 'title': 'A'}]}])


def test_build_interactive_list_payload_requires_button():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='button_label'):
        build_interactive_list_payload('hi', '', [{'rows': [{'id': '1', 'title': 'A'}]}])


def test_build_interactive_list_payload_requires_sections():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='section'):
        build_interactive_list_payload('hi', 'go', [])


def test_build_interactive_list_payload_section_needs_rows():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='row'):
        build_interactive_list_payload('hi', 'go', [{'rows': []}])


def test_build_interactive_list_payload_row_needs_id_and_title():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError, match='id and title'):
        build_interactive_list_payload('hi', 'go', [{'rows': [{'id': '', 'title': 'A'}]}])


def test_build_interactive_list_payload_with_descriptions_and_header():
    from app.services.whatsapp import build_interactive_list_payload
    out = build_interactive_list_payload(
        'body', 'pick',
        [{'title': 'Section A', 'rows': [
            {'id': '1', 'title': 'A', 'description': 'desc'},
            {'id': '2', 'title': 'B'},
        ]}],
        header_text='Header',
        footer_text='Footer',
    )
    assert out['header']['text'] == 'Header'
    assert out['footer']['text'] == 'Footer'
    assert out['action']['sections'][0]['title'] == 'Section A'
    assert out['action']['sections'][0]['rows'][0]['description'] == 'desc'


def test_build_interactive_list_payload_caps_total_rows():
    from app.services.whatsapp import build_interactive_list_payload, MAX_INTERACTIVE_LIST_ROWS
    too_many = [{'id': f'r{i}', 'title': f'Row {i}'} for i in range(MAX_INTERACTIVE_LIST_ROWS + 5)]
    out = build_interactive_list_payload('b', 'g', [{'rows': too_many}])
    # Only MAX rows survive
    total = sum(len(s['rows']) for s in out['action']['sections'])
    assert total == MAX_INTERACTIVE_LIST_ROWS


# ─── build_interactive_button_payload edge cases ──────────────────────────


def test_build_interactive_button_payload_too_long_title():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError, match='20 characters'):
        build_interactive_button_payload(
            'body',
            [{'id': 'b1', 'title': 'x' * 21}],
        )


def test_build_interactive_button_payload_with_header_and_footer():
    from app.services.whatsapp import build_interactive_button_payload
    out = build_interactive_button_payload(
        'body',
        [{'id': 'b1', 'title': 'A'}, {'id': 'b2', 'title': 'B'}],
        header_text='Header',
        footer_text='Footer',
    )
    assert out['header']['text'] == 'Header'
    assert out['footer']['text'] == 'Footer'


# ─── build_template_message_payload ───────────────────────────────────────


def test_build_template_message_payload_no_name():
    from app.services.whatsapp import build_template_message_payload
    with pytest.raises(ValueError):
        build_template_message_payload('', 'es')


def test_build_template_message_payload_with_components():
    from app.services.whatsapp import build_template_message_payload
    out = build_template_message_payload(
        'tpl', 'es',
        components=[{'type': 'header', 'parameters': [{'type': 'text', 'text': 'H'}]}],
    )
    assert out['components'][0]['type'] == 'header'


def test_build_template_message_payload_with_variables():
    from app.services.whatsapp import build_template_message_payload
    out = build_template_message_payload('tpl', 'es', variables={'1': 'a', '2': 'b'})
    assert out['components'][0]['parameters'][0]['text'] == 'a'


# ─── build_whatsapp_message_payload error paths ───────────────────────────


def test_build_whatsapp_message_payload_text():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'text', text='hola')
    assert out['text']['body'] == 'hola'


def test_build_whatsapp_message_payload_interactive_needs_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError, match='interactive_payload'):
        build_whatsapp_message_payload('+57', 'interactive', interactive_payload=None)


def test_build_whatsapp_message_payload_template_needs_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError, match='template_payload'):
        build_whatsapp_message_payload('+57', 'template', template_payload=None)


def test_build_whatsapp_message_payload_media_needs_id_or_url():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError, match='media_id or media_url'):
        build_whatsapp_message_payload('+57', 'image', media_id=None, media_url=None)


def test_build_whatsapp_message_payload_image_with_caption():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'image', media_id='123', caption='cap')
    assert out['image']['caption'] == 'cap'


def test_build_whatsapp_message_payload_video_uses_text_as_caption():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'video', media_id='123', text='ttl')
    assert out['video']['caption'] == 'ttl'


def test_build_whatsapp_message_payload_audio_no_caption():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'audio', media_url='https://x.com/a.mp3', text='caption')
    # audio doesn't accept caption
    assert 'caption' not in out['audio']


def test_build_whatsapp_message_payload_template_with_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'template',
                                         template_payload={'name': 'hello', 'language': {'code': 'es'}})
    assert out['template']['name'] == 'hello'


def test_build_whatsapp_message_payload_interactive_with_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    out = build_whatsapp_message_payload('+57', 'interactive', interactive_payload={'type': 'button'})
    assert out['interactive']['type'] == 'button'


# ─── download_whatsapp_media (mocked httpx) ───────────────────────────────


class _FakeStreamResponse:
    def __init__(self, *, headers=None, chunks=None, status_code=200):
        self.headers = headers or {}
        self.status_code = status_code
        self._chunks = chunks or [b'data']

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('GET', 'http://x')
            raise httpx.HTTPStatusError('bad', request=req, response=httpx.Response(self.status_code, request=req))


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class _FakeAsyncClient:
    """Pluggable AsyncClient that supports stream() and get() calls."""

    def __init__(self, *, stream_response=None, get_response=None, **kw):
        self.stream_response = stream_response
        self.get_response = get_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, headers=None):
        return _FakeStreamCtx(self.stream_response)

    async def get(self, url, headers=None):
        return self.get_response


class _FakeGetResp:
    def __init__(self, *, json_payload, status_code=200):
        self._j = json_payload
        self.status_code = status_code

    def json(self):
        return self._j

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('GET', 'http://x')
            raise httpx.HTTPStatusError('bad', request=req, response=httpx.Response(self.status_code, request=req))


def test_download_whatsapp_media_no_url(monkeypatch, tmp_path):
    """media_info from Graph doesn't include URL → RuntimeError."""
    from app.services import whatsapp

    # Set up a real secret to bypass meta_token_is_configured check
    secrets_dir = tmp_path / 'secrets'
    secrets_dir.mkdir()
    secret_file = secrets_dir / 'sec.txt'
    secret_file.write_text('EAAB-realtoken-1234567890')
    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    async def _fake_info(media_id, token_ref):
        return {'mime_type': 'image/png'}  # no 'url' key

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    with pytest.raises(RuntimeError, match='media download URL'):
        asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))


def test_download_whatsapp_media_validation_failure(monkeypatch):
    """If the Meta-returned URL fails the outbound URL guard → RuntimeError."""
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    async def _fake_info(media_id, token_ref):
        return {'url': 'http://evil.example.com/leak', 'mime_type': 'image/png'}

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    with pytest.raises(RuntimeError, match='validation'):
        asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))


def test_download_whatsapp_media_no_token(monkeypatch):
    """Token resolves to local-mock → RuntimeError."""
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'local-mock-token')

    async def _fake_info(media_id, token_ref):
        return {'url': 'https://lookaside.fbsbx.com/whatsapp_business/attachments/1', 'mime_type': 'image/png'}

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    with pytest.raises(RuntimeError, match='real Meta access token'):
        asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))


def test_download_whatsapp_media_content_length_too_large(monkeypatch):
    from app.services import whatsapp
    from app.services.whatsapp import WhatsAppMediaTooLargeError

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    async def _fake_info(media_id, token_ref):
        return {'url': 'https://lookaside.fbsbx.com/whatsapp_business/attachments/1', 'mime_type': 'image/png'}

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    # Force a small max_bytes via settings
    from app.core.config import get_settings as _orig_gs
    real_settings = _orig_gs()

    class _S:
        knowledge_file_max_bytes = 5
        meta_graph_version = real_settings.meta_graph_version

    monkeypatch.setattr(whatsapp, 'get_settings', lambda: _S())

    resp = _FakeStreamResponse(headers={'content-length': '100'})

    def _factory(**kw):
        return _FakeAsyncClient(stream_response=resp)

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)

    with pytest.raises(WhatsAppMediaTooLargeError) as exc:
        asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))
    assert exc.value.phase == 'preflight'


def test_download_whatsapp_media_streamed_too_large(monkeypatch):
    from app.services import whatsapp
    from app.services.whatsapp import WhatsAppMediaTooLargeError

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    async def _fake_info(media_id, token_ref):
        return {'url': 'https://lookaside.fbsbx.com/whatsapp_business/attachments/1', 'mime_type': 'image/png'}

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    from app.core.config import get_settings as _orig_gs
    real_settings = _orig_gs()

    class _S:
        knowledge_file_max_bytes = 5
        meta_graph_version = real_settings.meta_graph_version

    monkeypatch.setattr(whatsapp, 'get_settings', lambda: _S())

    # No content-length header, but the chunks add up beyond max
    resp = _FakeStreamResponse(
        headers={'content-type': 'image/png'},
        chunks=[b'aa', b'bb', b'ccccccc'],
    )

    def _factory(**kw):
        return _FakeAsyncClient(stream_response=resp)

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)

    with pytest.raises(WhatsAppMediaTooLargeError) as exc:
        asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))
    assert exc.value.phase == 'streamed'


def test_download_whatsapp_media_success(monkeypatch):
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    async def _fake_info(media_id, token_ref):
        return {'url': 'https://lookaside.fbsbx.com/whatsapp_business/attachments/1', 'mime_type': 'image/png'}

    monkeypatch.setattr(whatsapp, 'get_whatsapp_media_info', _fake_info)

    from app.core.config import get_settings as _orig_gs
    real_settings = _orig_gs()

    class _S:
        knowledge_file_max_bytes = 1_000_000
        meta_graph_version = real_settings.meta_graph_version

    monkeypatch.setattr(whatsapp, 'get_settings', lambda: _S())

    resp = _FakeStreamResponse(
        headers={'content-type': 'image/png', 'content-length': '4'},
        chunks=[b'ok!\n'],
    )

    def _factory(**kw):
        return _FakeAsyncClient(stream_response=resp)

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)

    data, ct = asyncio.run(whatsapp.download_whatsapp_media('123', 'sm://ref'))
    assert data == b'ok!\n'
    assert ct == 'image/png'


# ─── get_whatsapp_media_info ──────────────────────────────────────────────


def test_get_whatsapp_media_info_no_token(monkeypatch):
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'local-mock-token')

    with pytest.raises(RuntimeError, match='real Meta access token'):
        asyncio.run(whatsapp.get_whatsapp_media_info(media_id='123', token_ref=None))


def test_get_whatsapp_media_info_invalid_media_id(monkeypatch):
    """A non-numeric media_id is rejected."""
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    with pytest.raises(Exception):  # url_guard raises something
        asyncio.run(whatsapp.get_whatsapp_media_info(media_id='../escape', token_ref='r'))


def test_get_whatsapp_media_info_success(monkeypatch):
    from app.services import whatsapp

    monkeypatch.setattr(whatsapp, 'resolve_secret_ref', lambda r: 'EAAB-realtoken-1234567890')

    resp = _FakeGetResp(json_payload={'url': 'https://lookaside.fbsbx.com/x', 'mime_type': 'image/png'})

    def _factory(**kw):
        return _FakeAsyncClient(get_response=resp)

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)

    out = asyncio.run(whatsapp.get_whatsapp_media_info(media_id='123456789012', token_ref='r'))
    assert out['url'].startswith('https://')


# ─── token / secret ref helpers ───────────────────────────────────────────


def test_token_ref_is_configured_with_change_me():
    from app.services.whatsapp import meta_token_is_configured
    assert meta_token_is_configured('change-me-token') is False


def test_token_ref_is_configured_with_local_mock():
    from app.services.whatsapp import meta_token_is_configured
    assert meta_token_is_configured('local-mock-token') is False


def test_token_ref_is_configured_with_real():
    from app.services.whatsapp import meta_token_is_configured
    assert meta_token_is_configured('EAAB-token') is True


def test_normalize_meta_app_secret_with_pipe():
    from app.services.whatsapp import normalize_meta_app_secret
    out = normalize_meta_app_secret('appid|appsecret')
    assert out == 'appsecret'


def test_normalize_meta_app_secret_no_pipe():
    from app.services.whatsapp import normalize_meta_app_secret
    out = normalize_meta_app_secret('justsecret')
    assert out == 'justsecret'


def test_normalize_meta_app_secret_empty():
    from app.services.whatsapp import normalize_meta_app_secret
    assert normalize_meta_app_secret('') is None
    assert normalize_meta_app_secret(None) is None


def test_normalize_meta_app_secret_pipe_with_empty_side():
    from app.services.whatsapp import normalize_meta_app_secret
    out = normalize_meta_app_secret('|secret')
    # Empty appid → falls through to the joined form
    assert '|' in out
