"""Tests para `copiloto_core.email.providers.factory.make_email_provider`."""
from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from copiloto_core.email.providers.base import ProviderInvalidConfig
from copiloto_core.email.providers.factory import make_email_provider
from copiloto_core.email.providers.mailgun import MailgunProvider
from copiloto_core.email.providers.resend import ResendProvider
from copiloto_core.email.providers.sendgrid import SendGridProvider
from copiloto_core.email.providers.smtp import SMTPProvider


@pytest.fixture
def master_key(monkeypatch):
    """Inyecta una master Fernet en Settings para que `_decrypt_secret` funcione."""
    key = Fernet.generate_key().decode('ascii')
    # admin_routes._get_secret_cipher lee de get_settings(), monkeypatcheamos
    # settings.ai_provider_master_key a una key real.
    from copiloto_core.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'ai_provider_master_key', key, raising=False)
    return key


def _cipher_text(key: str, plaintext: str) -> str:
    return Fernet(key.encode('ascii')).encrypt(plaintext.encode('utf-8')).decode('ascii')


def _row(**overrides):
    base = {
        'id': 'r1',
        'code': 'resend-test',
        'provider_type': 'resend',
        'name': 'Test',
        'config_jsonb': {},
        'api_key_ciphertext': None,  # to fill
        'from_address_override': None,
        'from_name_override': None,
    }
    base.update(overrides)
    return base


def test_make_resend(master_key):
    row = _row(api_key_ciphertext=_cipher_text(master_key, 're_xxx'))
    adapter = make_email_provider(
        row, fallback_from_address='global@x.com', fallback_from_name='Global',
    )
    assert isinstance(adapter, ResendProvider)
    assert adapter.provider_code == 'resend-test'


def test_make_sendgrid(master_key):
    row = _row(
        code='sg-1', provider_type='sendgrid',
        api_key_ciphertext=_cipher_text(master_key, 'SG.x'),
    )
    adapter = make_email_provider(
        row, fallback_from_address='g@x.com', fallback_from_name='G',
    )
    assert isinstance(adapter, SendGridProvider)


def test_make_mailgun(master_key):
    row = _row(
        code='mg-1', provider_type='mailgun',
        config_jsonb={'domain': 'mg.x.com', 'region': 'us'},
        api_key_ciphertext=_cipher_text(master_key, 'mg-key'),
    )
    adapter = make_email_provider(
        row, fallback_from_address='g@x.com', fallback_from_name='G',
    )
    assert isinstance(adapter, MailgunProvider)


def test_make_smtp(master_key):
    row = _row(
        code='smtp-1', provider_type='smtp',
        config_jsonb={
            'host': 'smtp.example.com', 'port': 587,
            'username': 'me', 'use_tls': True,
        },
        api_key_ciphertext=_cipher_text(master_key, 'pw'),
    )
    adapter = make_email_provider(
        row, fallback_from_address='g@x.com', fallback_from_name='G',
    )
    assert isinstance(adapter, SMTPProvider)


def test_make_unknown_provider_type_raises(master_key):
    # Tiene que pasar una ciphertext válida para no fallar en _decrypt antes
    # de llegar al raise por unknown provider_type.
    row = _row(
        provider_type='unsupported',
        api_key_ciphertext=_cipher_text(master_key, 'x'),
    )
    with pytest.raises(ValueError, match='unknown email provider_type'):
        make_email_provider(
            row,
            fallback_from_address='x@x.com', fallback_from_name='X',
        )


def test_make_with_empty_ciphertext_raises_invalid_config():
    """Sin api_key_ciphertext el factory debe levantar ProviderInvalidConfig."""
    with pytest.raises(ProviderInvalidConfig, match='api_key_ciphertext'):
        make_email_provider(
            _row(api_key_ciphertext=None),
            fallback_from_address='x@x.com', fallback_from_name='X',
        )


def test_make_uses_override_when_present(master_key):
    row = _row(
        api_key_ciphertext=_cipher_text(master_key, 're_x'),
        from_address_override='custom@x.com',
        from_name_override='Custom',
    )
    adapter = make_email_provider(
        row, fallback_from_address='global@x.com', fallback_from_name='Global',
    )
    assert adapter._from_address == 'custom@x.com'
    assert adapter._from_name == 'Custom'


def test_make_falls_back_when_override_absent(master_key):
    row = _row(api_key_ciphertext=_cipher_text(master_key, 're_x'))
    adapter = make_email_provider(
        row, fallback_from_address='global@x.com', fallback_from_name='Global',
    )
    assert adapter._from_address == 'global@x.com'
    assert adapter._from_name == 'Global'


def test_make_handles_config_jsonb_as_string(master_key):
    """asyncpg con jsonb devuelve dict, pero algunos paths (mock con str) deben funcionar."""
    row = _row(
        provider_type='mailgun',
        config_jsonb='{"domain": "mg.x.com", "region": "eu"}',  # ← string
        api_key_ciphertext=_cipher_text(master_key, 'k'),
    )
    adapter = make_email_provider(
        row, fallback_from_address='x@x.com', fallback_from_name='X',
    )
    assert isinstance(adapter, MailgunProvider)
    assert adapter._region == 'eu'
