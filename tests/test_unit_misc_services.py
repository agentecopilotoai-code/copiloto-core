"""Combined tests for low-coverage services that are pure helpers.

Covers:
- app/services/promotions.py
- app/services/payment_provider.py
- app/chatbot/intent_classifier.py
- app/services/media_storage.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime

import pytest


# ═════════════════════════════════════════════════════════════════════════
# promotions.py — promo_caption is the only pure helper
# ═════════════════════════════════════════════════════════════════════════


def test_promo_caption_with_all_fields():
    from app.services.promotions import promo_caption
    out = promo_caption({
        'name': 'Black Friday',
        'description': 'Aprovecha hoy',
        'discount_percent': 25,
        'coupon_code': 'BF25',
        'valid_until': datetime(2026, 12, 31),
    })
    assert 'Black Friday' in out
    assert 'Aprovecha hoy' in out
    assert '25% de descuento' in out
    assert 'BF25' in out
    assert '31/12/2026' in out


def test_promo_caption_with_only_coupon():
    from app.services.promotions import promo_caption
    out = promo_caption({'coupon_code': 'WELCOME10'})
    assert 'WELCOME10' in out


def test_promo_caption_with_invalid_discount():
    from app.services.promotions import promo_caption
    out = promo_caption({'name': 'X', 'discount_percent': 'not a number'})
    assert 'X' in out


def test_promo_caption_empty_returns_fallback():
    from app.services.promotions import promo_caption
    assert promo_caption({}) == 'Promoción activa'


def test_promo_caption_invalid_date_swallowed():
    """If `valid_until.strftime` raises, the helper just skips it."""
    from app.services.promotions import promo_caption

    class _BadDate:
        def strftime(self, fmt):
            raise RuntimeError('bad date')

    out = promo_caption({'name': 'Promo', 'valid_until': _BadDate()})
    assert 'Promo' in out


# ═════════════════════════════════════════════════════════════════════════
# payment_provider.py
# ═════════════════════════════════════════════════════════════════════════


def test_normalize_provider_accepts_known():
    from app.services.payment_provider import (
        PaymentProviderError,
        normalize_provider,
    )
    assert normalize_provider('mercadopago') == 'mercadopago'
    assert normalize_provider('Stripe') == 'stripe'
    assert normalize_provider('none') == 'none'
    # Empty / None → rejected (not normalized to 'none')
    with pytest.raises(PaymentProviderError):
        normalize_provider(None)
    with pytest.raises(PaymentProviderError):
        normalize_provider('')


def test_normalize_provider_rejects_unknown():
    from app.services.payment_provider import (
        PaymentProviderError,
        normalize_provider,
    )
    with pytest.raises(PaymentProviderError):
        normalize_provider('paypal')


def test_amount_to_cents_handles_various_inputs():
    from app.services.payment_provider import _amount_to_cents
    from decimal import Decimal
    assert _amount_to_cents(10) == 1000
    assert _amount_to_cents(10.5) == 1050
    assert _amount_to_cents(Decimal('19.99')) == 1999
    assert _amount_to_cents('5.25') == 525


# ──── generate_payment_link guard rails ──────────────────────────────────


def test_generate_payment_link_rejects_no_provider():
    from app.services.payment_provider import (
        PaymentProviderError,
        generate_payment_link,
    )

    async def _go():
        return await generate_payment_link(
            provider='none', api_key='k', amount=100,
            currency='COP', description='x', external_ref='r',
        )

    with pytest.raises(PaymentProviderError):
        asyncio.run(_go())


def test_generate_payment_link_rejects_missing_api_key():
    from app.services.payment_provider import (
        PaymentProviderError,
        generate_payment_link,
    )

    async def _go():
        return await generate_payment_link(
            provider='mercadopago', api_key='', amount=100,
            currency='COP', description='x', external_ref='r',
        )

    with pytest.raises(PaymentProviderError):
        asyncio.run(_go())


def test_generate_payment_link_rejects_invalid_amount():
    from app.services.payment_provider import (
        PaymentProviderError,
        generate_payment_link,
    )

    async def _go():
        return await generate_payment_link(
            provider='mercadopago', api_key='k', amount='abc',
            currency='COP', description='x', external_ref='r',
        )

    with pytest.raises(PaymentProviderError):
        asyncio.run(_go())


def test_generate_payment_link_rejects_zero_amount():
    from app.services.payment_provider import (
        PaymentProviderError,
        generate_payment_link,
    )

    async def _go():
        return await generate_payment_link(
            provider='mercadopago', api_key='k', amount=0,
            currency='COP', description='x', external_ref='r',
        )

    with pytest.raises(PaymentProviderError):
        asyncio.run(_go())


def test_generate_payment_link_rejects_invalid_currency():
    from app.services.payment_provider import (
        PaymentProviderError,
        generate_payment_link,
    )

    async def _go():
        return await generate_payment_link(
            provider='mercadopago', api_key='k', amount=100,
            currency='XX', description='x', external_ref='r',
        )

    with pytest.raises(PaymentProviderError):
        asyncio.run(_go())


# ──── verify_mercadopago_signature ───────────────────────────────────────


def test_verify_mercadopago_signature_no_secret_or_header():
    from app.services.payment_provider import verify_mercadopago_signature
    assert verify_mercadopago_signature(b'body', None, 'secret') is False
    assert verify_mercadopago_signature(b'body', 'ts=1,v1=a', None) is False


def test_verify_mercadopago_signature_missing_v1():
    from app.services.payment_provider import verify_mercadopago_signature
    assert verify_mercadopago_signature(b'body', 'ts=1', 'secret') is False


def test_verify_mercadopago_signature_freshness_requires_ts():
    from app.services.payment_provider import verify_mercadopago_signature
    assert verify_mercadopago_signature(
        b'body', 'v1=abc', 'secret', now_ts=1000, tolerance_seconds=60,
    ) is False


def test_verify_mercadopago_signature_freshness_rejects_old():
    from app.services.payment_provider import verify_mercadopago_signature
    assert verify_mercadopago_signature(
        b'body', 'ts=100,v1=abc', 'secret',
        now_ts=10000, tolerance_seconds=60,
    ) is False


def test_verify_mercadopago_signature_valid_raw_payload():
    from app.services.payment_provider import verify_mercadopago_signature
    secret = 'mp_secret'
    body = b'{"x":1}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    header = f'ts=1700,v1={sig}'
    assert verify_mercadopago_signature(body, header, secret) is True


def test_verify_mercadopago_signature_valid_manifest_form():
    from app.services.payment_provider import verify_mercadopago_signature
    secret = 's'
    manifest = 'id:DATA;request-id:REQ;ts:1700;'
    sig = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    header = f'ts=1700,v1={sig}'
    assert verify_mercadopago_signature(
        b'{}', header, secret, data_id='DATA', request_id='REQ',
    ) is True


# ──── verify_stripe_signature ────────────────────────────────────────────


def test_verify_stripe_signature_no_secret_or_header():
    from app.services.payment_provider import verify_stripe_signature
    assert verify_stripe_signature(b'body', None, 'secret') is False
    assert verify_stripe_signature(b'body', 't=1,v1=abc', None) is False


def test_verify_stripe_signature_missing_t():
    from app.services.payment_provider import verify_stripe_signature
    assert verify_stripe_signature(b'body', 'v1=abc', 'secret') is False


def test_verify_stripe_signature_missing_v1():
    from app.services.payment_provider import verify_stripe_signature
    assert verify_stripe_signature(b'body', 't=1700', 'secret') is False


def test_verify_stripe_signature_valid():
    from app.services.payment_provider import verify_stripe_signature
    secret = 'whsec_test'
    body = b'{"event":"x"}'
    ts = '1700'
    signed = f'{ts}.{body.decode()}'
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    header = f't={ts},v1={sig}'
    assert verify_stripe_signature(body, header, secret) is True


def test_verify_stripe_signature_rejects_stale():
    from app.services.payment_provider import verify_stripe_signature
    secret = 's'
    body = b'{}'
    sig = hmac.new(secret.encode(), b'100.{}', hashlib.sha256).hexdigest()
    header = f't=100,v1={sig}'
    assert verify_stripe_signature(
        body, header, secret, now_ts=10000, tolerance_seconds=60,
    ) is False


# ──── extract_external_ref / extract_payment_status ──────────────────────


def test_extract_external_ref_mercadopago_top_level():
    from app.services.payment_provider import extract_external_ref
    assert extract_external_ref('mercadopago', {'external_reference': 'r1'}) == 'r1'


def test_extract_external_ref_mercadopago_data_level():
    from app.services.payment_provider import extract_external_ref
    assert extract_external_ref(
        'mercadopago', {'data': {'external_reference': 'r2'}},
    ) == 'r2'


def test_extract_external_ref_mercadopago_resource_level():
    from app.services.payment_provider import extract_external_ref
    assert extract_external_ref(
        'mercadopago', {'resource': {'external_reference': 'r3'}},
    ) == 'r3'


def test_extract_external_ref_stripe():
    from app.services.payment_provider import extract_external_ref
    payload = {'data': {'object': {'metadata': {'external_ref': 'sr1'}}}}
    assert extract_external_ref('stripe', payload) == 'sr1'


def test_extract_external_ref_returns_none_for_none_provider():
    from app.services.payment_provider import extract_external_ref
    assert extract_external_ref('none', {}) is None


def test_extract_external_ref_missing_field():
    from app.services.payment_provider import extract_external_ref
    assert extract_external_ref('mercadopago', {}) is None
    assert extract_external_ref('stripe', {}) is None


def test_extract_payment_status_mercadopago_approved():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status('mercadopago', {'status': 'approved'}) == 'paid'


def test_extract_payment_status_mercadopago_rejected_to_failed():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status(
        'mercadopago', {'data': {'status': 'rejected'}},
    ) == 'failed'


def test_extract_payment_status_mercadopago_refunded():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status(
        'mercadopago', {'resource': {'status': 'refunded'}},
    ) == 'refunded'


def test_extract_payment_status_stripe_succeeded():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status(
        'stripe', {'type': 'checkout.session.completed'},
    ) == 'paid'
    assert extract_payment_status(
        'stripe', {'type': 'payment_intent.succeeded'},
    ) == 'paid'


def test_extract_payment_status_stripe_failed():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status(
        'stripe', {'type': 'payment_intent.payment_failed'},
    ) == 'failed'


def test_extract_payment_status_stripe_refunded():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status('stripe', {'type': 'charge.refunded'}) == 'refunded'


def test_extract_payment_status_none_or_unknown():
    from app.services.payment_provider import extract_payment_status
    assert extract_payment_status('stripe', {'type': 'invoice.paid'}) is None
    assert extract_payment_status('none', {}) is None
    assert extract_payment_status('mercadopago', {}) is None


# ═════════════════════════════════════════════════════════════════════════
# intent_classifier.py — pure helpers + cascade outcomes
# ═════════════════════════════════════════════════════════════════════════


def test_compile_tenant_rules_filters_unknown_intents():
    from app.chatbot.intent_classifier import _compile_tenant_rules
    rules = _compile_tenant_rules({
        'book_appointment': ['agendar', 'reserva'],
        'unknown_intent': ['x'],  # filtered
        'greeting': [],  # empty list filtered
    })
    intents = {intent for _, intent, _ in rules}
    assert 'book_appointment' in intents
    assert 'unknown_intent' not in intents
    assert 'greeting' not in intents


def test_compile_tenant_rules_compiles_word_boundaries():
    from app.chatbot.intent_classifier import _compile_tenant_rules
    rules = _compile_tenant_rules({'book_appointment': ['cita']})
    pat, intent, conf = rules[0]
    assert pat.search('quiero una cita') is not None
    # word boundary: 'citado' does NOT match
    assert pat.search('estoy citado pero...') is None


def test_rule_classify_greeting():
    from app.chatbot.intent_classifier import (
        ALL_INTENTS,
        _rule_classify,
    )
    out = _rule_classify('hola', set(ALL_INTENTS), [])
    assert out is not None
    assert out.intent == 'greeting'
    assert out.resolved_by == 'rule'


def test_rule_classify_book_appointment():
    from app.chatbot.intent_classifier import (
        ALL_INTENTS,
        _rule_classify,
    )
    out = _rule_classify('quiero agendar una cita', set(ALL_INTENTS), [])
    assert out is not None
    assert out.intent == 'book_appointment'


def test_rule_classify_complaint():
    from app.chatbot.intent_classifier import (
        ALL_INTENTS,
        _rule_classify,
    )
    out = _rule_classify('esto es una estafa', set(ALL_INTENTS), [])
    assert out is not None
    assert out.intent == 'complaint_or_risk'
    assert out.confidence >= 0.85


def test_rule_classify_no_match_returns_none():
    from app.chatbot.intent_classifier import (
        ALL_INTENTS,
        _rule_classify,
    )
    out = _rule_classify('xyzzy plugh frobnitz', set(ALL_INTENTS), [])
    assert out is None


def test_rule_classify_respects_enabled_intents():
    from app.chatbot.intent_classifier import _rule_classify
    # Only allow `book_appointment`, but text is a greeting → returns None
    out = _rule_classify('hola', {'book_appointment'}, [])
    assert out is None


def test_classify_intent_resolves_rule_no_llm():
    """High-confidence rule path → returns immediately without invoking LLM."""
    from app.chatbot.intent_classifier import classify_intent

    class _Settings:
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1
        local_llm_base_url = None
        local_llm_model = None
        local_llm_timeout_seconds = 1

    async def _go():
        return await classify_intent(
            'hola', settings=_Settings(), tenant_no_train=True,
        )

    out = asyncio.run(_go())
    assert out.intent == 'greeting'
    assert out.resolved_by == 'rule'


def test_classify_intent_falls_back_to_faq_when_no_match():
    """No rule matches, no LLM configured → fallback faq."""
    from app.chatbot.intent_classifier import classify_intent

    class _Settings:
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1
        local_llm_base_url = None
        local_llm_model = None
        local_llm_timeout_seconds = 1

    async def _go():
        return await classify_intent(
            'xyzzy plugh frobnitz', settings=_Settings(), tenant_no_train=True,
        )

    out = asyncio.run(_go())
    assert out.intent == 'faq'
    assert out.resolved_by == 'fallback'


def test_classify_intent_with_tenant_custom_keywords():
    """A custom keyword maps to a high-confidence rule match."""
    from app.chatbot.intent_classifier import classify_intent

    class _Settings:
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1
        local_llm_base_url = None
        local_llm_model = None
        local_llm_timeout_seconds = 1

    async def _go():
        return await classify_intent(
            'agendar', settings=_Settings(),
            tenant_config={
                'custom_keywords': {'book_appointment': ['agendar']},
            },
            tenant_no_train=True,
        )

    out = asyncio.run(_go())
    assert out.intent == 'book_appointment'


def test_classify_intent_respects_enabled_intents_filter():
    """If `greeting` is disabled, a "hola" should NOT classify as greeting."""
    from app.chatbot.intent_classifier import classify_intent

    class _Settings:
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1
        local_llm_base_url = None
        local_llm_model = None
        local_llm_timeout_seconds = 1

    async def _go():
        return await classify_intent(
            'hola', settings=_Settings(),
            tenant_config={'enabled_intents': ['book_appointment', 'faq']},
            tenant_no_train=True,
        )

    out = asyncio.run(_go())
    # not greeting; falls back to faq
    assert out.intent != 'greeting'


def test_classify_intent_empty_enabled_intents_uses_all():
    """An empty enabled_intents list → falls back to ALL_INTENTS."""
    from app.chatbot.intent_classifier import classify_intent

    class _Settings:
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1
        local_llm_base_url = None
        local_llm_model = None
        local_llm_timeout_seconds = 1

    async def _go():
        return await classify_intent(
            'hola', settings=_Settings(),
            tenant_config={'enabled_intents': []},
            tenant_no_train=True,
        )

    out = asyncio.run(_go())
    assert out.intent == 'greeting'


def test_intent_result_dataclass_default_layer_detail():
    from app.chatbot.intent_classifier import IntentResult
    ir = IntentResult(intent='greeting', confidence=0.9, resolved_by='rule')
    assert ir.layer_detail == ''


# ═════════════════════════════════════════════════════════════════════════
# media_storage.py — pure helpers
# ═════════════════════════════════════════════════════════════════════════


def test_safe_storage_segment_sanitizes_unsafe_chars():
    from app.services.media_storage import _safe_storage_segment
    # The sub replaces unsafe runs with a single '-', then trailing strip
    # removes the trailing dash
    assert _safe_storage_segment('hola mundo!@#') == 'hola-mundo'
    # all unsafe → fallback to 'file'
    assert _safe_storage_segment('!@#$%^') == 'file'


def test_safe_storage_segment_truncates_long_names():
    from app.services.media_storage import _safe_storage_segment
    out = _safe_storage_segment('x' * 500)
    assert len(out) <= 180


def test_safe_storage_segment_strips_leading_trailing_dots_dashes():
    from app.services.media_storage import _safe_storage_segment
    assert _safe_storage_segment('  ...hello-.-') == 'hello'


def test_media_object_key_format():
    from app.services.media_storage import media_object_key
    key = media_object_key(
        tenant_id='t1', asset_id='a1',
        filename='photo.jpg', digest='abcdef1234567890' + 'x' * 50,
    )
    assert key.startswith('media/t1/a1/')
    assert 'photo.jpg' in key


def test_validate_media_upload_rejects_unknown_kind():
    from app.services.media_storage import validate_media_upload
    with pytest.raises(ValueError, match='Unsupported media kind'):
        validate_media_upload(b'data', kind='sticker', filename='x', mime_type='image/png')


def test_validate_media_upload_rejects_missing_filename():
    from app.services.media_storage import validate_media_upload
    with pytest.raises(ValueError, match='filename'):
        validate_media_upload(b'data', kind='image', filename='', mime_type='image/png')


def test_validate_media_upload_rejects_empty_data():
    from app.services.media_storage import validate_media_upload
    with pytest.raises(ValueError, match='empty'):
        validate_media_upload(b'', kind='image', filename='x.png', mime_type='image/png')


def test_validate_media_upload_rejects_oversized():
    from app.services.media_storage import validate_media_upload
    # image cap = 5MB
    big = b'x' * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='exceeds'):
        validate_media_upload(big, kind='image', filename='x.png', mime_type='image/png')


def test_validate_media_upload_rejects_bad_mime():
    from app.services.media_storage import validate_media_upload
    with pytest.raises(ValueError, match='MIME'):
        validate_media_upload(b'x', kind='image', filename='x.gif', mime_type='image/gif')


def test_validate_media_upload_strips_mime_params():
    from app.services.media_storage import validate_media_upload
    out = validate_media_upload(
        b'x', kind='image', filename='x.png', mime_type='image/png; charset=binary',
    )
    assert out == 'image/png'


# ──── store_media_file (local backend, tmp_path) ─────────────────────────


def test_store_media_file_local_writes_to_disk(tmp_path):
    from app.core.config import Settings
    from app.services.media_storage import store_media_file
    settings = Settings.model_construct(
        knowledge_storage_backend='local',
        knowledge_storage_local_path=str(tmp_path),
    )
    out = store_media_file(
        data=b'PNGDATA', tenant_id='t1', asset_id='a1', kind='image',
        filename='hello.png', mime_type='image/png', settings=settings,
    )
    assert out.storage_backend == 'local'
    assert out.size_bytes == 7
    assert out.sha256 == hashlib.sha256(b'PNGDATA').hexdigest()
    assert out.bucket is None
    assert out.source_uri.startswith('file://')


def test_store_media_file_rejects_unsupported_backend(tmp_path):
    from app.core.config import Settings
    from app.services.media_storage import store_media_file
    settings = Settings.model_construct(
        knowledge_storage_backend='gcs',
        knowledge_storage_local_path=str(tmp_path),
    )
    with pytest.raises(ValueError, match='Unsupported storage backend'):
        store_media_file(
            data=b'x', tenant_id='t1', asset_id='a1', kind='image',
            filename='x.png', mime_type='image/png', settings=settings,
        )


# ──── read_media_file (local) ────────────────────────────────────────────


def test_read_media_file_local_reads_disk(tmp_path):
    from app.core.config import Settings
    from app.services.media_storage import read_media_file
    settings = Settings.model_construct(knowledge_storage_backend='local')

    file_path = tmp_path / 'sample.bin'
    file_path.write_bytes(b'CONTENT')
    data = read_media_file(
        storage_backend='local', object_key='media/t/x',
        source_uri=f'file://{file_path}', bucket=None, settings=settings,
    )
    assert data == b'CONTENT'


def test_read_media_file_local_missing_raises():
    from app.core.config import Settings
    from app.services.media_storage import read_media_file
    settings = Settings.model_construct(knowledge_storage_backend='local')
    with pytest.raises(FileNotFoundError):
        read_media_file(
            storage_backend='local', object_key='media/t/x',
            source_uri='file:///does-not-exist.bin', bucket=None,
            settings=settings,
        )


def test_read_media_file_local_requires_file_uri():
    from app.core.config import Settings
    from app.services.media_storage import read_media_file
    settings = Settings.model_construct()
    with pytest.raises(FileNotFoundError, match='source_uri'):
        read_media_file(
            storage_backend='local', object_key='x',
            source_uri='https://x', bucket=None, settings=settings,
        )


def test_read_media_file_s3_requires_bucket_and_key():
    from app.core.config import Settings
    from app.services.media_storage import read_media_file
    settings = Settings.model_construct()
    with pytest.raises(FileNotFoundError, match='bucket'):
        read_media_file(
            storage_backend='s3', object_key='', source_uri=None,
            bucket=None, settings=settings,
        )


def test_read_media_file_unsupported_backend():
    from app.core.config import Settings
    from app.services.media_storage import read_media_file
    settings = Settings.model_construct()
    with pytest.raises(ValueError, match='Unsupported storage backend'):
        read_media_file(
            storage_backend='gcs', object_key='x', source_uri=None,
            bucket=None, settings=settings,
        )


# ──── delete_media_file (local) ──────────────────────────────────────────


def test_delete_media_file_local_removes_file(tmp_path):
    from app.core.config import Settings
    from app.services.media_storage import delete_media_file
    settings = Settings.model_construct()

    target = tmp_path / 'file.bin'
    target.write_bytes(b'X')
    delete_media_file(
        storage_backend='local', object_key='media/t/x',
        source_uri=f'file://{target}', bucket=None, settings=settings,
    )
    assert not target.exists()


def test_delete_media_file_local_missing_source_uri_noop():
    from app.core.config import Settings
    from app.services.media_storage import delete_media_file
    settings = Settings.model_construct()
    # No source_uri → no-op (returns None silently)
    delete_media_file(
        storage_backend='local', object_key='x',
        source_uri=None, bucket=None, settings=settings,
    )


def test_delete_media_file_unsupported_backend_noop():
    from app.core.config import Settings
    from app.services.media_storage import delete_media_file
    settings = Settings.model_construct()
    # No-op on unknown backend (no raise)
    delete_media_file(
        storage_backend='gcs', object_key='x', source_uri=None,
        bucket=None, settings=settings,
    )
