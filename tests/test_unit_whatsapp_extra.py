"""Targeted tests for `app/services/whatsapp.py` — pure builders, sig check,
freshness check, normalizers, interactive parsers, and mocked send paths."""
from __future__ import annotations

import hashlib
import hmac

import pytest


# ───────── normalize_meta_app_secret ─────────────────────────────────────


def test_normalize_meta_app_secret_none_returns_none():
    from app.services.whatsapp import normalize_meta_app_secret
    assert normalize_meta_app_secret(None) is None
    assert normalize_meta_app_secret('') is None


def test_normalize_meta_app_secret_strips_app_id():
    from app.services.whatsapp import normalize_meta_app_secret
    assert normalize_meta_app_secret('123456|abc-secret') == 'abc-secret'


def test_normalize_meta_app_secret_no_pipe_returns_clean():
    from app.services.whatsapp import normalize_meta_app_secret
    assert normalize_meta_app_secret('  pure-secret  ') == 'pure-secret'


def test_normalize_meta_app_secret_empty_part_falls_back_to_cleaned():
    from app.services.whatsapp import normalize_meta_app_secret
    # if the app_id or secret are empty, returns the cleaned value as-is
    assert normalize_meta_app_secret('|onlysecret') == '|onlysecret'


# ───────── _secret_name_from_ref / resolve_secret_ref ────────────────────


def test_secret_name_from_ref_none_or_empty():
    from app.services.whatsapp import _secret_name_from_ref
    assert _secret_name_from_ref(None) is None
    assert _secret_name_from_ref('') is None


def test_secret_name_from_ref_must_have_prefix():
    from app.services.whatsapp import _secret_name_from_ref
    assert _secret_name_from_ref('plain-token') is None
    assert _secret_name_from_ref('secrets/wa_token') == 'wa_token'


def test_secret_name_from_ref_rejects_traversal():
    from app.services.whatsapp import _secret_name_from_ref
    assert _secret_name_from_ref('secrets/../etc/passwd') is None


def test_resolve_secret_ref_missing_returns_none():
    from app.services.whatsapp import resolve_secret_ref
    assert resolve_secret_ref(None) is None
    assert resolve_secret_ref('secrets/nonexistent_secret_xyz') is None


def test_resolve_secret_ref_reads_from_disk(tmp_path, monkeypatch):
    from app.services import whatsapp as wa
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'my_token').write_text('THE-TOKEN\n')

    def fake_paths(name: str):
        return [secret_dir / name]

    monkeypatch.setattr(wa, '_candidate_secret_paths', fake_paths)
    assert wa.resolve_secret_ref('secrets/my_token') == 'THE-TOKEN'


# ───────── token configured guards ───────────────────────────────────────


def test_meta_token_is_configured_rejects_placeholders():
    from app.services.whatsapp import meta_token_is_configured
    assert meta_token_is_configured(None) is False
    assert meta_token_is_configured('') is False
    assert meta_token_is_configured('change-me-please') is False
    assert meta_token_is_configured('local-mock-token') is False


def test_meta_token_is_configured_accepts_real():
    from app.services.whatsapp import meta_token_is_configured
    assert meta_token_is_configured('EAAGm0PX4ZCpsBO...realtoken') is True


def test_secret_ref_is_configured_false_when_unresolved():
    from app.services.whatsapp import secret_ref_is_configured
    assert secret_ref_is_configured('secrets/nonexistent') is False
    assert secret_ref_is_configured(None) is False


# ───────── verify_signature_with_secret ──────────────────────────────────


def test_verify_signature_with_secret_matches_correct_sig():
    from app.services.whatsapp import verify_signature_with_secret
    secret = 'super-secret'
    body = b'{"hello":"world"}'
    sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature_with_secret(body, sig, secret) is True


def test_verify_signature_with_secret_rejects_wrong():
    from app.services.whatsapp import verify_signature_with_secret
    assert verify_signature_with_secret(b'body', 'sha256=deadbeef', 'secret') is False


def test_verify_signature_with_secret_rejects_missing():
    from app.services.whatsapp import verify_signature_with_secret
    assert verify_signature_with_secret(b'body', None, 'secret') is False
    assert verify_signature_with_secret(b'body', 'sha256=anything', None) is False


# ───────── is_meta_message_fresh ─────────────────────────────────────────


def test_is_meta_message_fresh_disabled_when_max_age_zero():
    from app.services.whatsapp import is_meta_message_fresh
    assert is_meta_message_fresh({}, now_ts=10000, max_age_seconds=0) is True


def test_is_meta_message_fresh_rejects_missing_timestamp():
    from app.services.whatsapp import is_meta_message_fresh
    assert is_meta_message_fresh({}, now_ts=10000, max_age_seconds=60) is False


def test_is_meta_message_fresh_rejects_garbage_timestamp():
    from app.services.whatsapp import is_meta_message_fresh
    assert is_meta_message_fresh({'timestamp': 'abc'}, now_ts=10000, max_age_seconds=60) is False
    assert is_meta_message_fresh({'timestamp': -5}, now_ts=10000, max_age_seconds=60) is False


def test_is_meta_message_fresh_accepts_recent_message():
    from app.services.whatsapp import is_meta_message_fresh
    assert is_meta_message_fresh({'timestamp': '9990'}, now_ts=10000, max_age_seconds=60) is True


def test_is_meta_message_fresh_rejects_stale_message():
    from app.services.whatsapp import is_meta_message_fresh
    assert is_meta_message_fresh({'timestamp': '8000'}, now_ts=10000, max_age_seconds=60) is False


def test_is_meta_message_fresh_rejects_future_skew():
    from app.services.whatsapp import is_meta_message_fresh
    # 2 hours in future
    assert is_meta_message_fresh({'timestamp': 10000 + 7200}, now_ts=10000, max_age_seconds=60) is False


# ───────── build_interactive_button_payload ──────────────────────────────


def test_build_interactive_button_payload_happy():
    from app.services.whatsapp import build_interactive_button_payload
    payload = build_interactive_button_payload(
        body_text='Selecciona',
        buttons=[
            {'id': 'a', 'title': 'A'},
            {'id': 'b', 'title': 'B'},
        ],
        header_text='Header',
        footer_text='Footer',
    )
    assert payload['type'] == 'button'
    assert payload['body']['text'] == 'Selecciona'
    assert payload['header']['text'] == 'Header'
    assert payload['footer']['text'] == 'Footer'
    assert len(payload['action']['buttons']) == 2


def test_build_interactive_button_payload_rejects_empty_body():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError):
        build_interactive_button_payload('', [{'id': 'a', 'title': 'A'}])


def test_build_interactive_button_payload_rejects_no_buttons():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError):
        build_interactive_button_payload('Body', [])


def test_build_interactive_button_payload_rejects_too_many():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError):
        build_interactive_button_payload(
            'Body',
            [{'id': str(i), 'title': f'B{i}'} for i in range(4)],
        )


def test_build_interactive_button_payload_rejects_empty_button():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError):
        build_interactive_button_payload('Body', [{'id': '', 'title': 'X'}])


def test_build_interactive_button_payload_rejects_long_title():
    from app.services.whatsapp import build_interactive_button_payload
    with pytest.raises(ValueError):
        build_interactive_button_payload(
            'Body',
            [{'id': 'a', 'title': 'x' * 21}],
        )


# ───────── build_interactive_list_payload ────────────────────────────────


def test_build_interactive_list_payload_happy():
    from app.services.whatsapp import build_interactive_list_payload
    payload = build_interactive_list_payload(
        body_text='Pick',
        button_label='Ver',
        sections=[
            {'title': 'Sección', 'rows': [
                {'id': 'r1', 'title': 'Row1', 'description': 'd'},
                {'id': 'r2', 'title': 'Row2'},
            ]},
        ],
    )
    assert payload['type'] == 'list'
    assert payload['action']['button'] == 'Ver'
    rows = payload['action']['sections'][0]['rows']
    assert rows[0]['description'] == 'd'
    assert 'description' not in rows[1]


def test_build_interactive_list_payload_rejects_empty_body():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError):
        build_interactive_list_payload('', 'Btn', [{'rows': [{'id': 'r', 'title': 't'}]}])


def test_build_interactive_list_payload_rejects_empty_button_label():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError):
        build_interactive_list_payload('Body', '', [{'rows': [{'id': 'r', 'title': 't'}]}])


def test_build_interactive_list_payload_rejects_no_sections():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError):
        build_interactive_list_payload('Body', 'Btn', [])


def test_build_interactive_list_payload_rejects_section_no_rows():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError):
        build_interactive_list_payload('Body', 'Btn', [{'rows': []}])


def test_build_interactive_list_payload_rejects_empty_row():
    from app.services.whatsapp import build_interactive_list_payload
    with pytest.raises(ValueError):
        build_interactive_list_payload(
            'Body', 'Btn', [{'rows': [{'id': '', 'title': ''}]}],
        )


def test_build_interactive_list_payload_caps_total_rows():
    """If total rows exceed 10, the builder truncates."""
    from app.services.whatsapp import build_interactive_list_payload
    rows = [{'id': str(i), 'title': f'R{i}'} for i in range(15)]
    payload = build_interactive_list_payload('Body', 'Btn', [{'rows': rows}])
    total = sum(len(s['rows']) for s in payload['action']['sections'])
    assert total == 10


# ───────── build_template_message_payload ────────────────────────────────


def test_build_template_message_payload_happy():
    from app.services.whatsapp import build_template_message_payload
    payload = build_template_message_payload(
        template_name='hello_world',
        locale='es_CO',
        variables={'1': 'Pedro', '2': '50000'},
    )
    assert payload['name'] == 'hello_world'
    assert payload['language']['code'] == 'es_CO'
    body_comp = next(c for c in payload['components'] if c['type'] == 'body')
    assert body_comp['parameters'][0]['text'] == 'Pedro'


def test_build_template_message_payload_with_components_passthrough():
    from app.services.whatsapp import build_template_message_payload
    components = [{'type': 'header', 'parameters': [{'type': 'text', 'text': 'X'}]}]
    payload = build_template_message_payload(
        template_name='t',
        locale='es',
        components=components,
    )
    assert payload['components'] == components


def test_build_template_message_payload_default_locale():
    from app.services.whatsapp import build_template_message_payload
    payload = build_template_message_payload('t', None)
    assert payload['language']['code'] == 'es'


def test_build_template_message_payload_rejects_no_name():
    from app.services.whatsapp import build_template_message_payload
    with pytest.raises(ValueError):
        build_template_message_payload('', 'es')


# ───────── build_whatsapp_message_payload ────────────────────────────────


def test_build_whatsapp_message_payload_text():
    from app.services.whatsapp import build_whatsapp_message_payload
    payload = build_whatsapp_message_payload(
        to='5730099887766', message_type='text', text='Hola',
    )
    assert payload['to'] == '5730099887766'
    assert payload['type'] == 'text'
    assert payload['text']['body'] == 'Hola'


def test_build_whatsapp_message_payload_unsupported_fallbacks_to_text():
    from app.services.whatsapp import build_whatsapp_message_payload
    payload = build_whatsapp_message_payload(
        to='1', message_type='sticker', text='Hi',
    )
    assert payload['type'] == 'text'


def test_build_whatsapp_message_payload_interactive_requires_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError):
        build_whatsapp_message_payload(to='1', message_type='interactive')


def test_build_whatsapp_message_payload_template_requires_payload():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError):
        build_whatsapp_message_payload(to='1', message_type='template')


def test_build_whatsapp_message_payload_image_requires_media():
    from app.services.whatsapp import build_whatsapp_message_payload
    with pytest.raises(ValueError):
        build_whatsapp_message_payload(to='1', message_type='image')


def test_build_whatsapp_message_payload_image_with_media_id():
    from app.services.whatsapp import build_whatsapp_message_payload
    payload = build_whatsapp_message_payload(
        to='1', message_type='image', media_id='123', caption='Foto',
    )
    assert payload['type'] == 'image'
    assert payload['image']['id'] == '123'
    assert payload['image']['caption'] == 'Foto'


def test_build_whatsapp_message_payload_image_with_media_url():
    from app.services.whatsapp import build_whatsapp_message_payload
    payload = build_whatsapp_message_payload(
        to='1', message_type='image', media_url='https://example.com/x.jpg',
    )
    assert payload['image']['link'] == 'https://example.com/x.jpg'


def test_build_whatsapp_message_payload_audio_no_caption():
    """Audio doesn't take a caption."""
    from app.services.whatsapp import build_whatsapp_message_payload
    payload = build_whatsapp_message_payload(
        to='1', message_type='audio', media_id='42', caption='nope',
    )
    assert payload['audio']['id'] == '42'
    assert 'caption' not in payload['audio']


# ───────── parse_interactive_reply ───────────────────────────────────────


def test_parse_interactive_reply_button_ok():
    from app.services.whatsapp import parse_interactive_reply
    msg = {
        'interactive': {
            'type': 'button_reply',
            'button_reply': {'id': 'btn:1', 'title': 'OK'},
        },
    }
    out = parse_interactive_reply(msg)
    assert out == {
        'interactive_type': 'button_reply',
        'interactive_id': 'btn:1',
        'interactive_title': 'OK',
    }


def test_parse_interactive_reply_list_with_description():
    from app.services.whatsapp import parse_interactive_reply
    msg = {
        'interactive': {
            'type': 'list_reply',
            'list_reply': {'id': 'r1', 'title': 'Title', 'description': 'Desc'},
        },
    }
    out = parse_interactive_reply(msg)
    assert out['interactive_description'] == 'Desc'


def test_parse_interactive_reply_returns_none_for_unknown_type():
    from app.services.whatsapp import parse_interactive_reply
    msg = {'interactive': {'type': 'reaction'}}
    assert parse_interactive_reply(msg) is None


def test_parse_interactive_reply_returns_none_for_missing_interactive():
    from app.services.whatsapp import parse_interactive_reply
    assert parse_interactive_reply({}) is None
    assert parse_interactive_reply({'interactive': 'not a dict'}) is None
    assert parse_interactive_reply(None) is None


def test_parse_interactive_reply_returns_none_for_missing_id():
    from app.services.whatsapp import parse_interactive_reply
    msg = {'interactive': {'type': 'button_reply', 'button_reply': {'title': 'no id'}}}
    assert parse_interactive_reply(msg) is None


# ───────── template_components_for_meta ──────────────────────────────────


def test_template_components_for_meta_list_passthrough():
    from app.services.whatsapp import template_components_for_meta
    comps = [{'type': 'BODY', 'text': 'X'}, 'invalid']
    out = template_components_for_meta(comps)
    assert out == [{'type': 'BODY', 'text': 'X'}]


def test_template_components_for_meta_dict_shape():
    from app.services.whatsapp import template_components_for_meta
    comps = {
        'header': {'text': 'Hola'},
        'body': {'text': 'World'},
        'footer': {'text': 'Bye'},
        'buttons': [
            {'type': 'quick_reply', 'text': 'Yes'},
            {'text': 'No'},
        ],
    }
    out = template_components_for_meta(comps)
    types = [c['type'] for c in out]
    assert 'HEADER' in types
    assert 'BODY' in types
    assert 'FOOTER' in types
    assert 'BUTTONS' in types
    buttons = next(c for c in out if c['type'] == 'BUTTONS')
    assert len(buttons['buttons']) == 2


def test_template_components_for_meta_skips_blank_fields():
    from app.services.whatsapp import template_components_for_meta
    comps = {'header': {}, 'body': {'text': ''}, 'footer': {}}
    assert template_components_for_meta(comps) == []


def test_template_components_for_meta_none_returns_empty():
    from app.services.whatsapp import template_components_for_meta
    assert template_components_for_meta(None) == []
    assert template_components_for_meta('weird') == []


# ───────── send_whatsapp_message (mock mode) ─────────────────────────────


def test_send_whatsapp_message_mock_returns_envelope():
    import asyncio
    from app.services.whatsapp import send_whatsapp_message

    async def _go():
        return await send_whatsapp_message(
            phone_number_id='pn-1',
            to='5730099887766',
            message_type='text',
            text='Hola desde mock',
            delivery_mode='mock',
        )

    out = asyncio.run(_go())
    assert out['mocked'] is True
    assert out['delivery_mode'] == 'mock'
    assert out['text'] == 'Hola desde mock'
    assert out['message_type'] == 'text'


def test_send_whatsapp_message_live_requires_token(monkeypatch):
    import asyncio
    from app.services.whatsapp import send_whatsapp_message

    async def _go():
        return await send_whatsapp_message(
            phone_number_id='pn-1',
            to='1',
            message_type='text',
            text='hi',
            delivery_mode='live',
            token_ref='secrets/unresolvable',
        )

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


def test_send_text_message_delegates_to_send_whatsapp_message(monkeypatch):
    import asyncio
    from app.services import whatsapp as wa

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {'mocked': True}

    monkeypatch.setattr(wa, 'send_whatsapp_message', fake_send)

    async def _go():
        return await wa.send_text_message(
            phone_number_id='pn',
            to='1',
            text='Hola',
            delivery_mode='mock',
        )

    asyncio.run(_go())
    assert captured['message_type'] == 'text'
    assert captured['text'] == 'Hola'


def test_send_interactive_buttons_builds_payload(monkeypatch):
    import asyncio
    from app.services import whatsapp as wa

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {'mocked': True}

    monkeypatch.setattr(wa, 'send_whatsapp_message', fake_send)

    async def _go():
        return await wa.send_interactive_buttons(
            phone_number_id='pn', to='1', body_text='Hola',
            buttons=[{'id': 'a', 'title': 'A'}],
        )

    asyncio.run(_go())
    assert captured['message_type'] == 'interactive'
    assert captured['interactive_payload']['type'] == 'button'


def test_send_interactive_list_builds_payload(monkeypatch):
    import asyncio
    from app.services import whatsapp as wa

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {'mocked': True}

    monkeypatch.setattr(wa, 'send_whatsapp_message', fake_send)

    async def _go():
        return await wa.send_interactive_list(
            phone_number_id='pn', to='1', body_text='Pick', button_label='Ver',
            sections=[{'rows': [{'id': 'r', 'title': 'R'}]}],
        )

    asyncio.run(_go())
    assert captured['interactive_payload']['type'] == 'list'


def test_send_whatsapp_template_builds_payload(monkeypatch):
    import asyncio
    from app.services import whatsapp as wa

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {'mocked': True}

    monkeypatch.setattr(wa, 'send_whatsapp_message', fake_send)

    async def _go():
        return await wa.send_whatsapp_template(
            phone_number_id='pn', to='1', template_name='hello', locale='es',
            variables={'1': 'Mundo'},
        )

    asyncio.run(_go())
    assert captured['message_type'] == 'template'
    assert captured['template_payload']['name'] == 'hello'


# ───────── submit_template_to_meta / fetch / delete  guards ─────────────


def test_submit_template_to_meta_requires_token():
    import asyncio
    from app.services.whatsapp import submit_template_to_meta

    async def _go():
        return await submit_template_to_meta(
            waba_id='wb', token_ref='secrets/nonexistent',
            name='t', locale='es', category='utility', components={},
        )

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


def test_fetch_templates_from_meta_requires_token():
    import asyncio
    from app.services.whatsapp import fetch_templates_from_meta

    async def _go():
        return await fetch_templates_from_meta(waba_id='wb', token_ref=None)

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


def test_delete_template_from_meta_requires_token():
    import asyncio
    from app.services.whatsapp import delete_template_from_meta

    async def _go():
        return await delete_template_from_meta(
            waba_id='wb', token_ref=None, template_name='t',
        )

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


def test_get_whatsapp_media_info_requires_token():
    import asyncio
    from app.services.whatsapp import get_whatsapp_media_info

    async def _go():
        return await get_whatsapp_media_info(media_id='123', token_ref=None)

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


def test_whatsapp_media_too_large_error_carries_phase():
    from app.services.whatsapp import WhatsAppMediaTooLargeError
    err = WhatsAppMediaTooLargeError('preflight')
    assert err.phase == 'preflight'
    assert 'preflight' in str(err)
