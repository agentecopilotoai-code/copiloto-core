"""Sistema de email multi-provider del core (v2.0.0).

Diseño espejado del subsistema de IA (`copiloto_core.ai.*`):

- ``providers/base.py``           — ABC + dataclasses + excepciones tipadas.
- ``providers/{resend,sendgrid,mailgun,smtp}.py`` — 4 adapters concretos.
- ``providers/factory.py``        — instancia provider desde row de DB.
- ``dispatcher.py``               — fallback chain + audit por intento.

# Uso típico desde un caller (servicio que necesita mandar email)

    from copiloto_core.email import EmailDispatcher, EmailMessage

    dispatcher = EmailDispatcher()
    result = await dispatcher.send(conn, EmailMessage(
        to_address='user@example.com',
        subject='Hola',
        html='<p>Hola!</p>',
        text='Hola!',
        tags={'kind': 'welcome'},
    ))
    if not result.success:
        log.warning('email failed', error=result.error)

# BREAKING CHANGE — v2.0.0

Antes: `from copiloto_core.services.email import get_email_provider` que
leía `RESEND_API_KEY` del env. Ahora: el dispatcher recorre
`app.email_providers ORDER BY priority ASC`. Si no hay ningún provider
configurado, devuelve `ProviderResult(success=False,
error='no_providers_configured')` y el caller decide qué hacer.

El operador configura providers vía la UI
`/admin/platform/email-providers` (CRUD + test endpoint).
"""
from __future__ import annotations

from copiloto_core.email.dispatcher import EmailDispatcher
from copiloto_core.email.providers.base import (
    EmailMessage,
    EmailProvider,
    ProviderError,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)

__all__ = [
    'EmailDispatcher',
    'EmailMessage',
    'EmailProvider',
    'ProviderError',
    'ProviderInvalidConfig',
    'ProviderRateLimited',
    'ProviderRejected',
    'ProviderResult',
    'ProviderUnavailable',
]
