"""Static surface checks + unit tests for the web widget channel (TASK-0039)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.web_widget import (
    WEB_SESSION_TOKEN_AUDIENCE,
    build_lead_source,
    constant_time_equals,
    decode_session_token,
    generate_widget_token,
    hash_phone,
    issue_session_token,
    origin_is_allowed,
    synthesize_web_identity,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
MAIN = Path('app/main.py')
WORKER = Path('app/workers/event_worker.py')
WIDGET_JS = Path('admin-panel/public/widget.js')
ADMIN_API = Path('admin-panel/src/services/coreApi.js')
# UI-007.8: the WhatsApp module was redesigned into a feature directory; the
# WebWidgetPanel stays at its current path until its own UI task.
WHATSAPP_FEATURE = Path('admin-panel/src/features/owner-admin/whatsapp')
WEB_PANEL = Path('admin-panel/src/features/owner-admin/whatsapp/components/WebWidgetPanel.jsx')


def _whatsapp_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(WHATSAPP_FEATURE.rglob('*.js*'))
    )
ANALYTICS_PANEL = Path('admin-panel/src/features/owner-admin/analytics/AnalyticsPanel.jsx')


# ───── Schema changes ─────


def test_schema_allows_web_provider_in_tenant_channels():
    schema = SCHEMA.read_text()
    # TASK-0074 extended the enum to add Instagram and Facebook Messenger.
    # The check still includes 'web' so the widget channel keeps working.
    assert (
        "check (provider in ('whatsapp_cloud_api','web','instagram_messenger','facebook_messenger'))"
        in schema
    )


def test_schema_tenant_channels_has_allowed_origins_and_widget_config():
    schema = SCHEMA.read_text()
    assert "allowed_origins text[] not null default '{}'" in schema
    assert "widget_config jsonb not null default '{}'::jsonb" in schema


def test_schema_contacts_has_lead_source_jsonb():
    schema = SCHEMA.read_text()
    assert "lead_source jsonb not null default '{}'::jsonb" in schema
    assert 'gin_contacts_lead_source' in schema


# ───── Pydantic schemas ─────


def test_schemas_define_web_channel_models():
    text = SCHEMAS.read_text()
    assert 'class WebChannelUpsert' in text
    assert 'class WebChatStart' in text
    assert 'class WebChatMessage' in text
    assert 'rotate_widget_token' in text
    assert 'utm_source' in text and 'utm_campaign' in text and 'referrer' in text


# ───── API routes ─────


def test_routes_register_web_router_and_endpoints():
    text = ROUTES.read_text()
    assert "web_router = APIRouter(prefix='/web'" in text
    assert "@web_router.post('/chat/start'" in text
    assert "@web_router.post('/chat/{conversation_id}/messages'" in text
    assert "@web_router.get('/chat/{conversation_id}/messages'" in text
    assert 'router.include_router(web_router)' in text


def test_routes_admin_endpoints_for_web_channel():
    text = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/channels/web')" in text
    assert "@tenant_admin_router.put('/tenants/{tenant_id}/channels/web')" in text
    assert '_build_widget_snippet' in text


def test_routes_persist_lead_source_on_web_contact():
    text = ROUTES.read_text()
    # Web start endpoint must insert into contacts with lead_source column.
    assert 'lead_source' in text
    assert "source, metadata, lead_source" in text


def test_routes_analytics_overview_returns_lead_sources():
    text = ROUTES.read_text()
    assert "lead_source->>'channel'" in text
    assert "'lead_sources'" in text


def test_event_worker_skips_non_whatsapp_providers():
    # TASK-0074: the worker now dispatches WhatsApp + Instagram + Facebook
    # Messenger from the same queue. The 'web' provider remains excluded
    # because web widget responses are read by the widget itself (polling),
    # not pushed back via the worker.
    text = WORKER.read_text()
    assert (
        "c.provider in ('whatsapp_cloud_api','instagram_messenger','facebook_messenger')"
        in text
    )
    assert "'web'" not in text.split('where e.published_at is null')[1].split('order by')[0]


def test_main_adds_cors_middleware_for_web_widget():
    text = MAIN.read_text()
    assert 'web_widget_cors' in text
    assert 'Access-Control-Allow-Origin' in text


# ───── Admin panel wiring ─────


def test_core_api_exposes_web_channel_helpers():
    text = ADMIN_API.read_text()
    assert 'export function getWebChannel(' in text
    assert 'export function upsertWebChannel(' in text


def test_onboarding_renders_web_widget_tab():
    text = _whatsapp_feature_source()
    assert "import { WebWidgetPanel }" in text
    assert "id: 'web', label: 'Widget Web'" in text
    assert 'activeTab' in text


def test_web_widget_panel_uses_helpers():
    text = WEB_PANEL.read_text()
    assert "import { getWebChannel, upsertWebChannel }" in text
    assert 'rotate_widget_token' in text
    assert 'snippet' in text


def test_analytics_panel_renders_lead_sources():
    text = ANALYTICS_PANEL.read_text()
    assert 'Origen de leads' in text or 'lead_source' in text
    assert 'overview.lead_sources' in text


# ───── Embeddable widget.js ─────


def test_widget_js_is_self_contained_iife():
    text = WIDGET_JS.read_text()
    assert text.lstrip().startswith('/*')
    assert '(function ()' in text or '(function()' in text
    assert 'data-tenant' in text
    assert 'data-widget-token' in text
    # Endpoints actually called from the embedded script
    assert '/v1/web/chat/start' in text
    assert '/v1/web/chat/' in text
    assert 'utm_source' in text and 'utm_campaign' in text
    assert 'document.referrer' in text


# ───── Service helpers ─────


def test_generate_widget_token_returns_high_entropy_string():
    token = generate_widget_token()
    assert isinstance(token, str)
    assert len(token) >= 32


def test_constant_time_equals_handles_none_safely():
    assert constant_time_equals(None, 'x') is False
    assert constant_time_equals('x', None) is False
    assert constant_time_equals('abc', 'abc') is True
    assert constant_time_equals('abc', 'abd') is False


def test_origin_allowlist_empty_means_any_origin():
    assert origin_is_allowed('https://anyone.example', []) is True
    assert origin_is_allowed(None, []) is True


def test_origin_allowlist_matches_exact_origin_trailing_slash_insensitive():
    assert origin_is_allowed('https://site.example/', ['https://site.example']) is True
    assert origin_is_allowed('https://site.example', ['https://site.example/']) is True
    assert origin_is_allowed('https://other.example', ['https://site.example']) is False


def test_origin_allowlist_wildcard_supported():
    assert origin_is_allowed('https://anything.example', ['*']) is True


def test_hash_phone_is_deterministic_sha256():
    a = hash_phone('+573001234567')
    b = hash_phone('+573001234567')
    assert a == b
    assert len(a) == 32


def test_synthesize_web_identity_pair_is_stable_for_seed():
    wa, phone = synthesize_web_identity('seed-abc')
    wa2, phone2 = synthesize_web_identity('seed-abc')
    assert wa == wa2 and phone == phone2
    assert wa.startswith('web:') and phone.startswith('web:')
    # Different seeds yield different ids
    other_wa, _ = synthesize_web_identity('different-seed')
    assert other_wa != wa


def test_build_lead_source_captures_all_utm_fields():
    src = build_lead_source(
        utm_source='google',
        utm_medium='cpc',
        utm_campaign='spring',
        referrer='https://example.com/blog',
    )
    assert src['channel'] == 'web'
    assert src['utm_source'] == 'google'
    assert src['utm_medium'] == 'cpc'
    assert src['utm_campaign'] == 'spring'
    assert src['referrer'] == 'https://example.com/blog'
    # first_contact_at is an ISO-8601 timestamp
    assert datetime.fromisoformat(src['first_contact_at'])


def test_issue_and_decode_session_token_roundtrip():
    tenant_id = uuid4()
    conversation_id = uuid4()
    contact_id = uuid4()
    token, exp = issue_session_token(
        secret_key='unit-test-secret-key-32bytes!',
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        contact_id=contact_id,
        issuer='copilotoia-test',
    )
    assert token.count('.') == 2
    assert exp > datetime.now(timezone.utc) + timedelta(hours=23)
    payload = decode_session_token(
        token,
        secret_key='unit-test-secret-key-32bytes!',
        issuer='copilotoia-test',
    )
    assert payload['tenant_id'] == str(tenant_id)
    assert payload['conversation_id'] == str(conversation_id)
    assert payload['contact_id'] == str(contact_id)
    assert payload['aud'] == WEB_SESSION_TOKEN_AUDIENCE
    assert payload['kind'] == 'web_session'


def test_decode_session_token_rejects_wrong_secret():
    token, _ = issue_session_token(
        secret_key='unit-test-secret-key-32bytes!',
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        contact_id=uuid4(),
        issuer='copilotoia-test',
    )
    with pytest.raises(ValueError):
        decode_session_token(
            token,
            secret_key='different-secret-key-padding!!',
            issuer='copilotoia-test',
        )


def test_decode_session_token_rejects_expired_token():
    # Forge a token with a past exp claim to verify the decoder rejects it.
    from jose import jwt

    past = int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp())
    payload = {
        'iss': 'copilotoia-test',
        'aud': WEB_SESSION_TOKEN_AUDIENCE,
        'exp': past,
        'iat': past - 60,
        'tenant_id': str(uuid4()),
        'conversation_id': str(uuid4()),
        'contact_id': str(uuid4()),
        'kind': 'web_session',
    }
    raw = jwt.encode(payload, 'unit-test-secret-key-32bytes!', algorithm='HS256')
    with pytest.raises(ValueError):
        decode_session_token(
            raw,
            secret_key='unit-test-secret-key-32bytes!',
            issuer='copilotoia-test',
        )


def test_decode_session_token_rejects_wrong_audience_via_kind_check():
    # Mint a token with kind='other' to ensure the kind guard fires.
    from jose import jwt

    payload = {
        'iss': 'copilotoia-test',
        'aud': WEB_SESSION_TOKEN_AUDIENCE,
        'exp': int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        'kind': 'other',
    }
    raw = jwt.encode(payload, 'unit-test-secret-key-32bytes!', algorithm='HS256')
    with pytest.raises(ValueError):
        decode_session_token(
            raw,
            secret_key='unit-test-secret-key-32bytes!',
            issuer='copilotoia-test',
        )
