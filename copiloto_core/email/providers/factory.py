"""Factory: row de ``app.email_providers`` → instancia de adapter concreto.

Espeja el patrón de ``copiloto_core/ai/providers/factory.py``:

    >>> from copiloto_core.email.providers.factory import make_email_provider
    >>> adapter = make_email_provider(row, fallback_from_address=..., fallback_from_name=...)
    >>> result = await adapter.send(EmailMessage(...))

El caller debe haber leído la fila previamente bajo ``support_mode``
(RLS gated). La factory:

1. Resuelve el ``api_key_ciphertext`` → plaintext via Fernet (reusa la
   misma master key ``AI_PROVIDER_MASTER_KEY``; sin separar para no
   agregar otro env var).
2. Resuelve el sender efectivo: si la fila tiene `from_address_override`
   lo usa, sino cae al `fallback_from_address` del Settings global.
3. Instancia el adapter concreto. Si el `config_jsonb` shape está roto,
   el adapter levanta ``ProviderInvalidConfig``.

Si el provider_type no es uno de los 4 soportados, levanta ``ValueError``
— la DB tiene CHECK constraint que prevendría esto, pero defense-in-depth.
"""
from __future__ import annotations

from typing import Any

from copiloto_core.email.providers.base import (
    EmailProvider,
    ProviderInvalidConfig,
)


def _decrypt_api_key(ciphertext: str | bytes | None) -> str:
    """Descifra el `api_key_ciphertext` con la master key Fernet del env.

    Reusa ``copiloto_core.platform_admin.admin_routes._decrypt_secret`` para
    no duplicar la lógica. Levanta `ProviderInvalidConfig` si no hay
    ciphertext (provider mal configurado en DB) — el dispatcher lo trata
    como NOT retryable.
    """
    if not ciphertext:
        raise ProviderInvalidConfig(
            'api_key_ciphertext vacío: provider mal configurado'
        )
    # Lazy import — evita ciclo con admin_routes (que importa de la
    # cripto desde ai providers). El helper acepta bytes; si viene str
    # (text column de Postgres) hacemos el bytes() cast acá.
    from copiloto_core.platform_admin.admin_routes import (  # noqa: PLC0415
        _decrypt_secret,
    )

    if isinstance(ciphertext, str):
        # `app.email_providers.api_key_ciphertext` es text. Fernet acepta
        # tanto str como bytes-like; el helper hace `bytes(ciphertext)`
        # que rompe sobre str → encode a utf-8 explicitly.
        ciphertext = ciphertext.encode('utf-8')
    return _decrypt_secret(ciphertext)


def make_email_provider(
    row: dict[str, Any],
    *,
    fallback_from_address: str,
    fallback_from_name: str,
) -> EmailProvider:
    """Construye el adapter concreto para una fila de ``app.email_providers``.

    Args:
      row: dict-like (asyncpg.Record es compatible) con las columnas de
        ``email_providers``: ``code``, ``provider_type``, ``config_jsonb``,
        ``api_key_ciphertext``, ``from_address_override``,
        ``from_name_override``.
      fallback_from_address: sender global del Settings (usado si la fila
        no especifica `from_address_override`).
      fallback_from_name: idem para nombre humano.

    Returns:
      Instancia del adapter, ya validada (su __init__ levanta
      ``ProviderInvalidConfig`` si la config está rota — el caller la
      atrapa y la trata como NOT retryable).

    Raises:
      ValueError: si `provider_type` no está en {resend, sendgrid,
        mailgun, smtp}. Esto NUNCA debería ocurrir si el CHECK constraint
        del schema está vigente — pero defense-in-depth.
      ProviderInvalidConfig: si el ciphertext no se puede descifrar (master
        key rotada sin re-cifrar) o el `config_jsonb` shape está roto.
    """
    provider_type = (row.get('provider_type') or '').strip().lower()
    provider_code = row.get('code') or ''
    config = row.get('config_jsonb')
    if isinstance(config, str):
        # asyncpg con jsonb devuelve dict por default; algunos paths
        # (tests con SQLite mock, RAW SQL select) pueden devolver str.
        import json as _json  # noqa: PLC0415
        try:
            config = _json.loads(config)
        except _json.JSONDecodeError as exc:
            raise ProviderInvalidConfig(
                f'config_jsonb no es JSON válido: {exc}'
            ) from exc
    if not isinstance(config, dict):
        config = {}

    from_address = row.get('from_address_override') or fallback_from_address
    from_name = row.get('from_name_override') or fallback_from_name

    api_key = _decrypt_api_key(row.get('api_key_ciphertext'))

    kwargs = {
        'provider_code': provider_code,
        'api_key': api_key,
        'config': config,
        'from_address': from_address,
        'from_name': from_name,
    }

    if provider_type == 'resend':
        from copiloto_core.email.providers.resend import ResendProvider  # noqa: PLC0415
        return ResendProvider(**kwargs)
    if provider_type == 'sendgrid':
        from copiloto_core.email.providers.sendgrid import SendGridProvider  # noqa: PLC0415
        return SendGridProvider(**kwargs)
    if provider_type == 'mailgun':
        from copiloto_core.email.providers.mailgun import MailgunProvider  # noqa: PLC0415
        return MailgunProvider(**kwargs)
    if provider_type == 'smtp':
        from copiloto_core.email.providers.smtp import SMTPProvider  # noqa: PLC0415
        return SMTPProvider(**kwargs)

    raise ValueError(
        f'unknown email provider_type {provider_type!r}; '
        'expected one of: resend, sendgrid, mailgun, smtp'
    )


__all__ = ['make_email_provider']
