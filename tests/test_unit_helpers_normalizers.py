"""Unit tests for app/api/v1/_helpers/normalizers.py.

Pure dict/record transformations — no DB, no network.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


class _Row(dict):
    """Minimal asyncpg.Record stand-in (dict-like)."""

    def keys(self):  # type: ignore[override]
        return super().keys()


def test_normalize_messenger_channel_none_returns_none():
    from app.api.v1._helpers.normalizers import _normalize_messenger_channel
    assert _normalize_messenger_channel(None) is None


def test_normalize_messenger_channel_basic_flags():
    from app.api.v1._helpers.normalizers import _normalize_messenger_channel
    row = _Row(
        id=str(uuid4()),
        token_ref=None,
        app_secret_ref=None,
        verify_token_hash=b'\x00\x01\x02',
    )
    out = _normalize_messenger_channel(row)
    assert out is not None
    assert out['token_configured'] is False
    assert out['app_secret_configured'] is False
    assert out['verify_token_configured'] is True
    assert 'verify_token_hash' not in out


def test_normalize_messenger_channel_missing_verify_token_hash():
    from app.api.v1._helpers.normalizers import _normalize_messenger_channel
    row = _Row(id=str(uuid4()), token_ref=None, app_secret_ref=None, verify_token_hash=None)
    out = _normalize_messenger_channel(row)
    assert out['verify_token_configured'] is False


def test_normalize_web_channel_none_returns_none():
    from app.api.v1._helpers.normalizers import _normalize_web_channel
    assert _normalize_web_channel(None) is None


def test_normalize_web_channel_normalizes_origins_and_widget():
    from app.api.v1._helpers.normalizers import _normalize_web_channel
    row = _Row(
        id=str(uuid4()),
        allowed_origins=['https://a.com'],
        widget_config='{"primary_color": "#fff"}',
    )
    out = _normalize_web_channel(row)
    assert out['allowed_origins'] == ['https://a.com']
    assert out['widget_config'] == {'primary_color': '#fff'}


def test_normalize_web_channel_none_origins_become_list():
    from app.api.v1._helpers.normalizers import _normalize_web_channel
    row = _Row(id=str(uuid4()), allowed_origins=None, widget_config=None)
    out = _normalize_web_channel(row)
    assert out['allowed_origins'] == []
    assert out['widget_config'] == {}


def test_digest_subscription_to_dict_full_fields():
    from app.api.v1._helpers.normalizers import _digest_subscription_to_dict
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    row = _Row(
        id=uuid4(),
        recipient_email='admin@example.com',
        recipient_whatsapp='+57300',
        cadence='daily',
        enabled=True,
        last_sent_at=now,
        created_at=now,
        updated_at=now,
    )
    out = _digest_subscription_to_dict(row)
    assert out['recipient_email'] == 'admin@example.com'
    assert out['cadence'] == 'daily'
    assert out['enabled'] is True
    assert out['last_sent_at'].startswith('2026-05-18')


def test_digest_subscription_to_dict_handles_nulls():
    from app.api.v1._helpers.normalizers import _digest_subscription_to_dict
    row = _Row(
        id=uuid4(),
        recipient_email=None,
        recipient_whatsapp=None,
        cadence='weekly',
        enabled=False,
        last_sent_at=None,
        created_at=None,
        updated_at=None,
    )
    out = _digest_subscription_to_dict(row)
    assert out['recipient_email'] == ''
    assert out['recipient_whatsapp'] == ''
    assert out['last_sent_at'] is None
    assert out['created_at'] is None
    assert out['updated_at'] is None


def test_normalize_service_catalog_row_none():
    from app.api.v1._helpers.normalizers import normalize_service_catalog_row
    assert normalize_service_catalog_row(None) is None


def test_normalize_service_catalog_row_full():
    from app.api.v1._helpers.normalizers import normalize_service_catalog_row
    row = _Row(
        id=str(uuid4()),
        metadata='{"foo":"bar"}',
        applies_when='{"rule": 1}',
        price_amount=12.5,
    )
    out = normalize_service_catalog_row(row)
    assert out['metadata'] == {'foo': 'bar'}
    assert out['applies_when'] == {'rule': 1}
    assert out['price_amount'] == 12.5


def test_normalize_service_catalog_row_invalid_applies_when_json():
    from app.api.v1._helpers.normalizers import normalize_service_catalog_row
    row = _Row(
        id=str(uuid4()),
        metadata={},
        applies_when='not-valid-json',
        price_amount=None,
    )
    out = normalize_service_catalog_row(row)
    assert out['applies_when'] == {}


def test_normalize_service_catalog_row_empty_applies_when_string():
    from app.api.v1._helpers.normalizers import normalize_service_catalog_row
    row = _Row(
        id=str(uuid4()),
        metadata={},
        applies_when='',
        price_amount=None,
    )
    out = normalize_service_catalog_row(row)
    assert out['applies_when'] == {}


def test_normalize_service_catalog_row_null_applies_when_coerces_to_dict():
    from app.api.v1._helpers.normalizers import normalize_service_catalog_row
    row = _Row(
        id=str(uuid4()),
        metadata={},
        applies_when=None,
        price_amount=None,
    )
    out = normalize_service_catalog_row(row)
    assert out['applies_when'] == {}


def test_normalize_qualification_question_none():
    from app.api.v1._helpers.normalizers import normalize_qualification_question
    assert normalize_qualification_question(None) is None


def test_normalize_qualification_question_options_as_string():
    from app.api.v1._helpers.normalizers import normalize_qualification_question
    row = _Row(
        id=str(uuid4()),
        options='["a","b"]',
        applies_to_service_ids=[uuid4(), uuid4()],
    )
    out = normalize_qualification_question(row)
    assert out['options'] == ['a', 'b']
    assert len(out['applies_to_service_ids']) == 2


def test_normalize_qualification_question_options_invalid_json_becomes_empty():
    from app.api.v1._helpers.normalizers import normalize_qualification_question
    row = _Row(id=str(uuid4()), options='garbage', applies_to_service_ids=None)
    out = normalize_qualification_question(row)
    assert out['options'] == []
    assert out['applies_to_service_ids'] == []


def test_normalize_qualification_question_options_non_list_becomes_empty():
    from app.api.v1._helpers.normalizers import normalize_qualification_question
    row = _Row(id=str(uuid4()), options=None, applies_to_service_ids=[])
    out = normalize_qualification_question(row)
    assert out['options'] == []


def test_normalize_qualification_question_options_list_stays():
    from app.api.v1._helpers.normalizers import normalize_qualification_question
    row = _Row(id=str(uuid4()), options=['a', 'b'], applies_to_service_ids=[])
    out = normalize_qualification_question(row)
    assert out['options'] == ['a', 'b']


def test_normalize_media_asset_none():
    from app.api.v1._helpers.normalizers import normalize_media_asset
    assert normalize_media_asset(None) is None


def test_normalize_media_asset_tags_coerced_to_list():
    from app.api.v1._helpers.normalizers import normalize_media_asset
    row = _Row(id=str(uuid4()), tags=('a', 'b'))
    out = normalize_media_asset(row)
    assert out['tags'] == ['a', 'b']


def test_normalize_media_asset_null_tags_become_empty_list():
    from app.api.v1._helpers.normalizers import normalize_media_asset
    row = _Row(id=str(uuid4()), tags=None)
    out = normalize_media_asset(row)
    assert out['tags'] == []


def test_normalize_promotion_none():
    from app.api.v1._helpers.normalizers import normalize_promotion
    assert normalize_promotion(None) is None


def test_normalize_promotion_with_uuids_and_discount():
    from app.api.v1._helpers.normalizers import normalize_promotion
    row = _Row(
        id=str(uuid4()),
        applies_to_service_ids=[uuid4()],
        discount_percent=12.5,
    )
    out = normalize_promotion(row)
    assert len(out['applies_to_service_ids']) == 1
    assert out['discount_percent'] == 12.5


def test_normalize_promotion_no_services_no_discount():
    from app.api.v1._helpers.normalizers import normalize_promotion
    row = _Row(id=str(uuid4()), applies_to_service_ids=None, discount_percent=None)
    out = normalize_promotion(row)
    assert out['applies_to_service_ids'] == []
    assert out['discount_percent'] is None


def test_normalize_segment_row_none():
    from app.api.v1._helpers.normalizers import normalize_segment_row
    assert normalize_segment_row(None) is None


def test_normalize_segment_row_rules_parsed():
    from app.api.v1._helpers.normalizers import normalize_segment_row
    row = _Row(id=str(uuid4()), rules='{"x":1}')
    out = normalize_segment_row(row)
    assert out['rules'] == {'x': 1}


def test_normalize_segment_row_rules_empty():
    from app.api.v1._helpers.normalizers import normalize_segment_row
    row = _Row(id=str(uuid4()), rules=None)
    out = normalize_segment_row(row)
    assert out['rules'] == {}


def test_normalize_campaign_none():
    from app.api.v1._helpers.normalizers import normalize_campaign
    assert normalize_campaign(None) is None


def test_normalize_campaign_parses_jsons():
    from app.api.v1._helpers.normalizers import normalize_campaign
    row = _Row(
        id=str(uuid4()),
        template_variables='{"name":"x"}',
        segment_filter='{"vip":true}',
    )
    out = normalize_campaign(row)
    assert out['template_variables'] == {'name': 'x'}
    assert out['segment_filter'] == {'vip': True}


def test_normalize_campaign_handles_empty_jsons():
    from app.api.v1._helpers.normalizers import normalize_campaign
    row = _Row(id=str(uuid4()), template_variables=None, segment_filter=None)
    out = normalize_campaign(row)
    assert out['template_variables'] == {}
    assert out['segment_filter'] == {}


def test_legal_row_to_dict_full():
    from app.api.v1._helpers.normalizers import _legal_row_to_dict
    now = datetime(2026, 5, 18, tzinfo=UTC)
    row = _Row(
        id=uuid4(),
        tenant_id=uuid4(),
        kind='terms',
        language='es',
        version=2,
        title='Términos',
        content_md='# Hola',
        published_at=now,
        archived_at=now,
        created_at=now,
    )
    out = _legal_row_to_dict(row)
    assert out['kind'] == 'terms'
    assert out['language'] == 'es'
    assert out['title'] == 'Términos'
    assert out['published_at'].startswith('2026-05-18')


def test_legal_row_to_dict_with_nulls():
    from app.api.v1._helpers.normalizers import _legal_row_to_dict
    row = _Row(
        id=uuid4(),
        tenant_id=uuid4(),
        kind='privacy',
        language='en',
        version=1,
        title='x',
        content_md='',
        published_at=None,
        archived_at=None,
        created_at=None,
    )
    out = _legal_row_to_dict(row)
    assert out['published_at'] is None
    assert out['archived_at'] is None
    assert out['created_at'] is None


def test_serialize_profile_full_data():
    from app.api.v1._helpers.normalizers import _serialize_profile
    user_id = uuid4()
    now = datetime(2026, 5, 18, tzinfo=UTC)
    prefs = _Row(
        display_name='Custom',
        phone='+1',
        locale='es-CO',
        timezone='America/Bogota',
        theme_override='dark',
        auth0_synced_at=now,
    )
    user = _Row(
        email='u@e.com',
        display_name='Original',
        mfa_enabled=True,
        last_login_at=now,
    )
    out = _serialize_profile(prefs, user, user_id)
    assert out['user_id'] == str(user_id)
    assert out['email'] == 'u@e.com'
    assert out['display_name'] == 'Custom'  # prefs wins
    assert out['mfa_enabled'] is True
    assert out['last_login_at'].startswith('2026-05-18')


def test_serialize_profile_fallback_to_user_display_name():
    from app.api.v1._helpers.normalizers import _serialize_profile
    user_id = uuid4()
    prefs = _Row(
        display_name=None,
        phone=None,
        locale=None,
        timezone=None,
        theme_override=None,
        auth0_synced_at=None,
    )
    user = _Row(
        email='u@e.com',
        display_name='Auth0 Name',
        mfa_enabled=False,
        last_login_at=None,
    )
    out = _serialize_profile(prefs, user, user_id)
    assert out['display_name'] == 'Auth0 Name'
    assert out['auth0_synced_at'] is None
    assert out['last_login_at'] is None
