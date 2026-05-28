"""Email transaccional — wrapper provider-agnostic con backend Resend.

Diseño:

- `EmailProvider` interface abstracta → fácil swap a SES/SendGrid/SMTP.
- `ResendProvider` implementa la interface contra la API HTTP de Resend
  (https://resend.com/docs/api-reference/emails/send-email).
- `NoopProvider` para envs sin API key (dev / tests) — loguea pero NO manda.
- `get_email_provider()` cachea la instancia por process (idéntico al
  patrón de `auth0_admin`).

Por qué Resend específicamente: simple API, free tier 3K/mes, React Email
para templates, webhooks finos. Cambiable a SES con cambiar la clase.

Uso típico:

    from copiloto_core.services.email import get_email_provider, EmailMessage

    provider = get_email_provider()
    result = await provider.send(EmailMessage(
        to='invitee@example.com',
        subject='Te invitaron a CopilotoIA',
        html=html_body,
        text=text_body,
    ))
    # result.message_id queda en app.tenant_invitations.last_send_provider_message_id

Errores:
- `EmailNotConfiguredError` si no hay API key (NoopProvider lo emite cuando
  el caller explícitamente exige envío real).
- `EmailSendError` para fallos transient o permanentes del provider.
  El caller decide si reintentar o marcar la invitación como failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx
import structlog

from copiloto_core.core.config import get_settings

log = structlog.get_logger()


# ─── Exceptions ──────────────────────────────────────────────────────────


class EmailNotConfiguredError(RuntimeError):
    """Provider real exigido pero no hay credenciales."""


class EmailSendError(RuntimeError):
    """Provider devolvió error al intentar enviar. `status_code` puede ser
    None si fue error de conexión (no llegamos al provider)."""

    def __init__(self, message: str, status_code: int | None = None,
                 body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ─── DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmailMessage:
    """Mensaje a enviar. Provider-agnostic."""
    to: str
    subject: str
    html: str
    text: str
    # Opcional override del sender (default `email_from_*` del setting).
    from_address: str | None = None
    from_name: str | None = None
    # `reply_to` permite que el invitado responda al admin que invitó,
    # no a `noreply@`. Mejor UX.
    reply_to: str | None = None
    # Headers extra (e.g. `List-Unsubscribe` requerido por Gmail 2024+).
    headers: dict[str, str] = field(default_factory=dict)
    # `tags` quedan en Resend dashboard para filtrar (ej. type=invitation,
    # tenant=acme). Útil para diagnóstico y dashboards de provider.
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailSendResult:
    """Resultado del send. `message_id` lo persiste el caller en
    `tenant_invitations.last_send_provider_message_id` para correlar
    con webhooks futuros (delivered / bounced / complained)."""
    message_id: str
    provider: str
    delivered_at_provider: bool  # True si el provider aceptó (no implica
                                 # que llegó al inbox; eso lo confirma
                                 # el webhook).
    raw_response: dict[str, Any] = field(default_factory=dict)


# ─── Provider interface ──────────────────────────────────────────────────


class EmailProvider(Protocol):
    """Interface mínima que cualquier email provider debe implementar."""

    name: str

    async def send(self, message: EmailMessage) -> EmailSendResult: ...

    def is_real(self) -> bool:
        """True si manda emails de verdad. False si NoopProvider (dev)."""
        ...


# ─── Resend ──────────────────────────────────────────────────────────────


def _resolve_resend_api_key() -> str | None:
    """Lee la key de plaintext OR file (chmod 600 pattern). Igual que
    `auth0_admin._service_client_secret`."""
    settings = get_settings()
    if settings.resend_api_key:
        return settings.resend_api_key.strip()
    if settings.resend_api_key_file:
        path = Path(settings.resend_api_key_file)
        if path.exists():
            return path.read_text(encoding='utf-8').strip()
    return None


class ResendProvider:
    """Implementación con Resend HTTP API.

    Endpoint: POST https://api.resend.com/emails
    Auth: Bearer <api_key>
    Docs: https://resend.com/docs/api-reference/emails/send-email
    """

    name = 'resend'
    _base_url = 'https://api.resend.com'

    def __init__(self, api_key: str, default_from_address: str,
                 default_from_name: str) -> None:
        self._api_key = api_key
        self._default_from_address = default_from_address
        self._default_from_name = default_from_name

    def is_real(self) -> bool:
        return True

    async def send(self, message: EmailMessage) -> EmailSendResult:
        from_addr = message.from_address or self._default_from_address
        from_name = message.from_name or self._default_from_name
        # Resend espera `from` como string "Name <addr@d.com>".
        from_field = f'{from_name} <{from_addr}>' if from_name else from_addr

        payload: dict[str, Any] = {
            'from': from_field,
            'to': [message.to],
            'subject': message.subject,
            'html': message.html,
            'text': message.text,
        }
        if message.reply_to:
            payload['reply_to'] = message.reply_to
        if message.headers:
            payload['headers'] = message.headers
        if message.tags:
            # Resend acepta tags como list of {name, value}.
            payload['tags'] = [
                {'name': k, 'value': v} for k, v in message.tags.items()
            ]

        # PERF-001 — singleton compartido (lazy import para evitar import
        # circular en tests que monkeypatchean email).
        from copiloto_core.services.http_clients import get_resend_client  # noqa: PLC0415
        try:
            client = await get_resend_client()
            resp = await client.post(
                '/emails',  # base_url ya tiene `https://api.resend.com`
                headers={
                    'authorization': f'Bearer {self._api_key}',
                    'content-type': 'application/json',
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            log.error(
                'email.resend.transport_error',
                error=str(exc), to=_redact_email(message.to),
            )
            raise EmailSendError(f'resend_transport_error: {exc!s}') from exc

        if resp.status_code >= 400:
            log.error(
                'email.resend.error',
                status=resp.status_code, body=resp.text[:300],
                to=_redact_email(message.to),
            )
            raise EmailSendError(
                f'resend_http_{resp.status_code}',
                status_code=resp.status_code, body=resp.text,
            )

        body = resp.json() if resp.content else {}
        message_id = body.get('id') or ''
        log.info(
            'email.resend.sent',
            message_id=message_id,
            to=_redact_email(message.to),
            subject=message.subject[:80],
            tags=message.tags,
        )
        return EmailSendResult(
            message_id=message_id,
            provider=self.name,
            delivered_at_provider=True,
            raw_response=body,
        )


# ─── Noop (dev / tests) ──────────────────────────────────────────────────


class NoopProvider:
    """Loguea el intento pero no manda. Útil para dev local y tests."""

    name = 'noop'

    def is_real(self) -> bool:
        return False

    async def send(self, message: EmailMessage) -> EmailSendResult:
        log.info(
            'email.noop.would_send',
            to=_redact_email(message.to),
            subject=message.subject[:80],
            from_addr=message.from_address,
            text_preview=message.text[:200],
            tags=message.tags,
            hint='RESEND_API_KEY no configurado — email NO enviado',
        )
        return EmailSendResult(
            message_id='noop-' + _short_id(),
            provider=self.name,
            delivered_at_provider=False,
        )


# ─── Factory ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    """Singleton del provider — cachea para no releer la key file por request.

    Para tests usar `clear_email_provider_cache()` antes de monkeypatchear
    settings, o inyectar manualmente via `set_email_provider_for_tests()`.
    """
    settings = get_settings()
    api_key = _resolve_resend_api_key()
    if not api_key:
        log.warning(
            'email.provider.no_api_key',
            hint='Resend API key no configurada — usando NoopProvider. '
                 'Setear RESEND_API_KEY o RESEND_API_KEY_FILE.',
        )
        return NoopProvider()
    return ResendProvider(
        api_key=api_key,
        default_from_address=settings.email_from_address,
        default_from_name=settings.email_from_name,
    )


def clear_email_provider_cache() -> None:
    """Útil para tests — clearea el lru_cache para que el siguiente
    `get_email_provider()` re-lea settings."""
    get_email_provider.cache_clear()


# ─── Helpers internos ────────────────────────────────────────────────────


def _redact_email(addr: str) -> str:
    """Mostrar `a***@d.com` en logs. PII-safe."""
    if not addr or '@' not in addr:
        return '[invalid]'
    local, _, domain = addr.partition('@')
    if len(local) <= 2:
        masked = '*' * len(local)
    else:
        masked = local[0] + '*' * (len(local) - 2) + local[-1]
    return f'{masked}@{domain}'


def _short_id() -> str:
    """Random short id para noop fake message_id."""
    import secrets  # noqa: PLC0415
    return secrets.token_hex(8)
