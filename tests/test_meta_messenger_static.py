"""Static tests for TASK-0074: Instagram DM + Facebook Messenger channel.

These tests validate the new channel surface end-to-end at the source level:
the schema check constraints, the messenger adapter (signature, normalization,
24h window, send payload), the webhook routes, the worker integration with
the service-window gate, the admin upsert endpoint and the admin-panel module.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.meta_messenger import (
    META_MESSENGER_PROVIDERS,
    OutsideServiceWindowError,
    build_messenger_send_payload,
    expected_object_for_provider,
    is_within_service_window,
    normalize_messenger_events,
    recipient_id_from_payload,
    service_window_expiry,
    verify_messenger_signature,
)

DB_SCHEMA = Path('infra/postgres/01-schema.sql')
META_MESSENGER = Path('app/services/meta_messenger.py')
API_ROUTES = Path('app/api/v1/routes.py')
API_SCHEMAS = Path('app/api/v1/schemas.py')
EVENT_WORKER = Path('app/workers/event_worker.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
MODULES_REGISTRY = Path('admin-panel/src/data/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
# UI-007.9: the social-channels module was redesigned into a feature directory.
SOCIAL_FEATURE = Path('admin-panel/src/features/owner-admin/social-channels')


def _social_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(SOCIAL_FEATURE.rglob('*.js*'))
    )


# ─── schema ──────────────────────────────────────────────────────────────────


def test_tenant_channels_provider_check_extends_to_instagram_and_facebook():
    schema = DB_SCHEMA.read_text()
    assert (
        "provider in ('whatsapp_cloud_api','web','instagram_messenger','facebook_messenger')"
        in schema
    )
    # webhook_events_raw should accept Meta Messenger events too, otherwise the
    # raw event insert in the new webhook handler would violate the check.
    assert (
        "provider in ('whatsapp_cloud_api','mercadopago','stripe','instagram_messenger','facebook_messenger')"
        in schema
    )


def test_tenant_channels_has_page_and_ig_columns_and_service_window():
    schema = DB_SCHEMA.read_text()
    assert 'page_id text,' in schema
    assert 'instagram_account_id text,' in schema
    assert 'service_window_hours integer not null default 24' in schema
    assert 'check (service_window_hours > 0)' in schema
    assert 'ix_tenant_channels_page' in schema
    assert 'ix_tenant_channels_ig_account' in schema


# ─── messenger adapter ──────────────────────────────────────────────────────


def test_messenger_providers_constant_matches_check_constraint():
    assert META_MESSENGER_PROVIDERS == {'instagram_messenger', 'facebook_messenger'}
    assert expected_object_for_provider('instagram_messenger') == 'instagram'
    assert expected_object_for_provider('facebook_messenger') == 'page'
    assert expected_object_for_provider('whatsapp_cloud_api') is None


def test_messenger_signature_uses_same_hmac_as_whatsapp():
    body = b'{"object":"instagram"}'
    secret = 'super-secret'
    # Compute expected SHA256 HMAC the same way Meta does.
    import hashlib
    import hmac

    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_messenger_signature(body, expected, secret) is True
    assert verify_messenger_signature(body, 'sha256=deadbeef', secret) is False
    # Empty signature or empty secret should always fail.
    assert verify_messenger_signature(body, None, secret) is False
    assert verify_messenger_signature(body, expected, None) is False
    # The shared normalize_meta_app_secret should accept app_id|secret pairs.
    assert verify_messenger_signature(body, expected, f'12345|{secret}') is True


def test_recipient_id_extractor_prefers_messaging_recipient_and_validates_object():
    payload = {
        'object': 'instagram',
        'entry': [
            {
                'id': 'ENTRY-1',
                'messaging': [
                    {
                        'sender': {'id': 'USER_PSID'},
                        'recipient': {'id': 'IG_ACCOUNT_42'},
                        'timestamp': 1700000000000,
                        'message': {'mid': 'mid.123', 'text': 'hola'},
                    }
                ],
            }
        ],
    }
    assert recipient_id_from_payload('instagram_messenger', payload) == 'IG_ACCOUNT_42'
    # Wrong object → no match (we don't want a Facebook payload routed to an IG channel).
    fb_only = {**payload, 'object': 'page'}
    assert recipient_id_from_payload('instagram_messenger', fb_only) is None
    # Falls back to entry.id when no messaging block exists.
    page_status_only = {
        'object': 'page',
        'entry': [{'id': 'PAGE-7', 'changes': []}],
    }
    assert recipient_id_from_payload('facebook_messenger', page_status_only) == 'PAGE-7'


def test_normalize_messenger_events_handles_text_attachment_echo_and_reply():
    payload = {
        'object': 'page',
        'entry': [
            {
                'id': 'PAGE_1',
                'messaging': [
                    {
                        'sender': {'id': 'PSID_1'},
                        'recipient': {'id': 'PAGE_1'},
                        'timestamp': 1700000000000,
                        'message': {
                            'mid': 'mid.text.1',
                            'text': '¿A qué hora abren?',
                            'reply_to': {'mid': 'mid.prev.0'},
                        },
                    },
                    {
                        # Echo (outbound copy reflected by Meta) must be skipped.
                        'sender': {'id': 'PAGE_1'},
                        'recipient': {'id': 'PSID_1'},
                        'timestamp': 1700000001000,
                        'message': {
                            'mid': 'mid.echo',
                            'text': 'Buenos días',
                            'is_echo': True,
                        },
                    },
                    {
                        'sender': {'id': 'PSID_2'},
                        'recipient': {'id': 'PAGE_1'},
                        'timestamp': 1700000002000,
                        'message': {
                            'mid': 'mid.img.1',
                            'attachments': [
                                {
                                    'type': 'image',
                                    'payload': {'url': 'https://cdn.example.com/x.jpg'},
                                },
                            ],
                        },
                    },
                ],
            }
        ],
    }
    events = normalize_messenger_events('facebook_messenger', payload)
    assert len(events) == 2
    text_event, image_event = events
    assert text_event.message_type == 'text'
    assert text_event.body_text == '¿A qué hora abren?'
    assert text_event.reply_to_external_id == 'mid.prev.0'
    assert text_event.sender_id == 'PSID_1'
    assert text_event.external_message_id == 'mid.text.1'
    assert text_event.timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert image_event.message_type == 'image'
    assert image_event.mime_type == 'https://cdn.example.com/x.jpg'
    # Reject providers outside the messenger surface.
    assert normalize_messenger_events('whatsapp_cloud_api', payload) == []


def test_service_window_helper_respects_24h_and_custom_hours():
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    last_inbound = now - timedelta(hours=23, minutes=30)
    assert is_within_service_window(last_inbound, 24, now=now) is True
    expired = now - timedelta(hours=25)
    assert is_within_service_window(expired, 24, now=now) is False
    # Custom window: 12h channel rejects 13h gap.
    assert is_within_service_window(now - timedelta(hours=13), 12, now=now) is False
    # None inbound → always closed.
    assert is_within_service_window(None, 24, now=now) is False
    # service_window_expiry returns last_inbound + window.
    expiry = service_window_expiry(last_inbound, 24)
    assert expiry == last_inbound + timedelta(hours=24)


def test_build_messenger_send_payload_text_and_attachment_validations():
    text_payload = build_messenger_send_payload('PSID_X', text='hola')
    assert text_payload['recipient'] == {'id': 'PSID_X'}
    assert text_payload['messaging_type'] == 'RESPONSE'
    assert text_payload['message'] == {'text': 'hola'}
    media_payload = build_messenger_send_payload(
        'PSID_Y', media_url='https://cdn.example.com/v.mp4', media_type='video'
    )
    assert media_payload['message']['attachment']['type'] == 'video'
    assert media_payload['message']['attachment']['payload']['url'].endswith('v.mp4')
    with pytest.raises(ValueError):
        build_messenger_send_payload('', text='hola')
    with pytest.raises(ValueError):
        build_messenger_send_payload('PSID_X')  # no text, no media


@pytest.mark.asyncio
async def test_send_messenger_message_raises_outside_window_and_validates_provider():
    # Outside window → canonical error code surfaced.
    from app.services.meta_messenger import send_messenger_message

    with pytest.raises(OutsideServiceWindowError) as exc:
        await send_messenger_message(
            'instagram_messenger',
            'IG_ID',
            'PSID',
            text='hola',
            within_service_window=False,
        )
    assert 'outside_service_window' in str(exc.value)
    # Mock mode short-circuits even when window is open.
    result = await send_messenger_message(
        'facebook_messenger',
        'PAGE_ID',
        'PSID',
        text='hola',
        delivery_mode='mock',
        within_service_window=True,
    )
    assert result['mocked'] is True
    assert result['provider'] == 'facebook_messenger'
    with pytest.raises(ValueError):
        await send_messenger_message(
            'whatsapp_cloud_api', 'X', 'Y', text='hola', within_service_window=True
        )


# ─── webhook routes ──────────────────────────────────────────────────────────


def test_webhook_get_route_supports_meta_provider_path_and_verify_token_lookup():
    source = API_ROUTES.read_text()
    assert "@webhook_router.get('/meta/{provider}')" in source
    assert 'verify_messenger_webhook' in source
    assert 'META_MESSENGER_PROVIDERS' in source
    # Verify token lookup is per-provider so Instagram and Facebook have independent tokens.
    assert "f'{provider}_verify_token'" in source
    assert "hmac.compare_digest(verify_token, hub_verify_token)" in source


def test_webhook_post_route_validates_signature_and_persists_messages():
    source = API_ROUTES.read_text()
    assert "@webhook_router.post('/meta/{provider}'" in source
    assert 'receive_messenger_webhook' in source
    assert 'verify_messenger_signature(body, x_hub_signature_256, app_secret)' in source
    assert "raise HTTPException(status_code=401, detail='Invalid webhook signature')" in source
    # Stores the raw payload for replay / audit using the provider as discriminator.
    assert 'insert into app.webhook_events_raw (tenant_id, provider, event_type' in source
    # Routes to instagram_account_id vs page_id depending on provider.
    assert "lookup_column = (" in source
    assert "'instagram_account_id' if provider == 'instagram_messenger' else 'page_id'" in source
    # Inbound message rows reuse the existing messages schema and call the same orchestrator.
    assert 'insert into app.messages' in source
    assert "channel=provider" in source
    assert 'orchestrate_inbound_message(' in source


def test_webhook_post_sets_service_window_expiry_on_conversation():
    source = API_ROUTES.read_text()
    assert 'service_window_expiry(' in source
    assert 'service_window_expires_at=$' in source
    assert 'service_window_hours' in source


# ─── outbound worker ─────────────────────────────────────────────────────────


def test_event_worker_queries_messenger_channels_and_carries_window_fields():
    source = EVENT_WORKER.read_text()
    assert "c.provider in ('whatsapp_cloud_api','instagram_messenger','facebook_messenger')" in source
    assert 'c.page_id' in source
    assert 'c.instagram_account_id' in source
    assert 'cv.service_window_expires_at' in source
    assert 'c.service_window_hours' in source


def test_event_worker_dispatches_to_messenger_send_and_blocks_outside_window():
    source = EVENT_WORKER.read_text()
    assert 'send_messenger_message(' in source
    assert 'within_service_window=window_open' in source
    assert 'OutsideServiceWindowError' in source
    assert "error_code = 'outside_service_window'" in source
    # Metrics channel label flips per provider.
    assert "channel_label = 'whatsapp' if provider == 'whatsapp_cloud_api' else provider" in source
    assert 'channel=channel_label' in source


# ─── admin upsert endpoint ───────────────────────────────────────────────────


def test_messenger_channel_upsert_endpoint_writes_secrets_and_audits():
    source = API_ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/channels/messenger')" in source
    assert "@tenant_admin_router.put('/tenants/{tenant_id}/channels/messenger')" in source
    assert 'def list_messenger_channels(' in source
    assert 'def upsert_messenger_channel(' in source
    assert "tenant_secret_ref(tenant_id, f'{provider}_access_token')" in source
    assert "tenant_secret_ref(tenant_id, f'{provider}_app_secret')" in source
    assert "tenant_secret_ref(tenant_id, f'{provider}_verify_token')" in source
    assert "action='channel.messenger_upserted'" in source
    assert 'verify_token_hash=coalesce(' in source


def test_messenger_channel_upsert_schema_enforces_provider_and_window():
    source = API_SCHEMAS.read_text()
    assert 'class MessengerChannelUpsert(BaseModel)' in source
    assert "MESSENGER_PROVIDER_PATTERN = '^(instagram_messenger|facebook_messenger)$'" in source
    assert 'provider: str = Field(pattern=MESSENGER_PROVIDER_PATTERN)' in source
    assert 'service_window_hours: int = Field(default=24, ge=1, le=168)' in source
    assert "verify_token: str | None = Field(default=None, min_length=16)" in source


# ─── admin panel UI ──────────────────────────────────────────────────────────


def test_admin_panel_registers_social_channels_module_with_admin_role():
    registry = MODULES_REGISTRY.read_text()
    layout = ADMIN_LAYOUT.read_text()
    core_api = CORE_API.read_text()
    assert "id: 'social-channels'" in registry
    # UI-005: minRole → capability de la matriz de permisos.
    assert "capability: 'social_channels.write'" in registry
    assert 'SocialChannelsModule' in layout
    assert "'social-channels': {" in layout
    assert 'listMessengerChannels' in core_api
    assert 'upsertMessengerChannel' in core_api
    assert '/channels/messenger' in core_api


def test_social_channels_module_renders_both_providers_and_window_input():
    module = _social_feature_source()
    assert "id: 'instagram_messenger'" in module
    assert "id: 'facebook_messenger'" in module
    assert 'service_window_hours' in module
    assert 'recipient_account_id' in module
    assert 'app_secret' in module
    assert 'verify_token' in module
    assert 'account_mode' in module
    assert "minLength={16}" in module
    assert 'upsertMessengerChannel' in module
