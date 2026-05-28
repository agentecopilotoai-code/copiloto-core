"""Tests para `copiloto_core.platform_admin.email_provider_routes`.

Valida solo el shape de los pydantic models (CRUD smoke). Los tests
end-to-end con FastAPI + RLS viven en `tests/test_e2e_*` (requires_db).
"""
from __future__ import annotations

import pytest

from copiloto_core.platform_admin.email_provider_routes import (
    EmailProviderCreate,
    EmailProviderRow,
    EmailProviderTestRequest,
    EmailProviderUpdate,
)


def test_create_payload_minimal_valid():
    payload = EmailProviderCreate(
        code='resend-main',
        provider_type='resend',
        name='Resend principal',
        api_key='re_xxx',
    )
    assert payload.is_active is True  # default
    assert payload.priority == 100    # default
    assert payload.config_jsonb == {}


def test_create_payload_rejects_unknown_provider_type():
    with pytest.raises(Exception):  # pydantic.ValidationError
        EmailProviderCreate(
            code='c', provider_type='unsupported',
            name='n', api_key='k',
        )


def test_create_payload_rejects_extra_fields():
    with pytest.raises(Exception):
        EmailProviderCreate(
            code='c', provider_type='resend',
            name='n', api_key='k', unknown_field=True,
        )


def test_create_payload_code_pattern():
    """Code debe ser lowercase + dígitos + dash/underscore."""
    with pytest.raises(Exception):
        EmailProviderCreate(
            code='Bad Code With Spaces!',
            provider_type='resend', name='n', api_key='k',
        )


def test_create_payload_rejects_bad_email():
    with pytest.raises(Exception):
        EmailProviderCreate(
            code='c', provider_type='resend', name='n', api_key='k',
            from_address_override='not-an-email',
        )


def test_update_payload_all_optional():
    """PATCH permite enviar 0 campos (otro layer del handler valida)."""
    EmailProviderUpdate()  # no raise


def test_update_payload_partial():
    payload = EmailProviderUpdate(is_active=False)
    assert payload.is_active is False
    assert payload.code is None


def test_test_request_requires_to_address():
    with pytest.raises(Exception):
        EmailProviderTestRequest()


def test_test_request_validates_email_shape():
    with pytest.raises(Exception):
        EmailProviderTestRequest(to_address='not-email')
    EmailProviderTestRequest(to_address='valid@example.com')


def test_row_response_serialization():
    """Smoke: el response model serializa sin error."""
    row = EmailProviderRow(
        id='id-1',
        code='resend-main',
        provider_type='resend',
        name='Resend',
        config_jsonb={},
        has_api_key=True,
        from_address_override=None,
        from_name_override=None,
        is_active=True,
        priority=100,
        created_at='2026-01-01T00:00:00',
        updated_at='2026-01-01T00:00:00',
    )
    assert row.has_api_key is True
