"""Compat shim del subsistema de email — v2.0.0.

# BREAKING CHANGE — ver `docs/EMAIL.md`

Antes (≤1.6.x): este módulo tenía un `ResendProvider` hardcodeado que
leía `RESEND_API_KEY` del env, y un `NoopProvider` para envs sin la key.

Ahora (≥2.0.0): la verdad vive en `app.email_providers` (DB) — uno o
más providers (Resend, SendGrid, Mailgun, SMTP) con priority chain. El
operador platform_owner los configura desde
`/admin/platform/email-providers`.

Este módulo expone una API compatible (`EmailMessage`, `EmailSendResult`,
`get_email_provider`, etc.) para que los callers legacy
(`copiloto_core.services.invitations`) sigan funcionando sin reescritura
masiva.

Internamente:

- `get_email_provider()` devuelve un wrapper sobre `EmailDispatcher` que
  adquiere connection del pool on-demand, traduce `EmailSendResult` ↔
  `ProviderResult`, y traduce errores tipados ↔ `EmailSendError`.
- Si no hay ningún provider configurado en DB → devuelve `NoopProvider`
  (idem comportamiento anterior con `RESEND_API_KEY` ausente).

NUEVOS proyectos deberían usar `copiloto_core.email.EmailDispatcher`
directamente — esta shim queda solo para back-compat con el código del
core ya escrito.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

log = structlog.get_logger()


# ─── Exceptions (compat con la API vieja) ──────────────────────────────────


class EmailNotConfiguredError(RuntimeError):
    """Provider real exigido pero no hay credenciales.

    En v2.0.0 esto significa: `app.email_providers` está vacía y el caller
    requirió un envío real (no NoopProvider).
    """


class EmailSendError(RuntimeError):
    """Provider devolvió error al intentar enviar."""

    def __init__(self, message: str, status_code: int | None = None,
                 body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ─── DTOs (mantienen la firma vieja para back-compat) ──────────────────────


@dataclass(frozen=True)
class EmailMessage:
    """Mensaje provider-agnostic (API vieja). El campo `to` (no
    `to_address`) se preserva para no romper callers."""
    to: str
    subject: str
    html: str
    text: str
    from_address: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailSendResult:
    """Resultado del send (API vieja). `delivered_at_provider=False`
    significa que el provider lo encoló (NoopProvider o dispatcher sin
    providers configurados)."""
    message_id: str
    provider: str
    delivered_at_provider: bool
    raw_response: dict[str, Any] = field(default_factory=dict)


# ─── Provider Protocol ────────────────────────────────────────────────────


class EmailProvider(Protocol):
    name: str
    async def send(self, message: EmailMessage) -> EmailSendResult: ...
    def is_real(self) -> bool: ...


# ─── Implementaciones ─────────────────────────────────────────────────────


class _DispatcherBackedProvider:
    """Wrapper que delega cada send al nuevo `EmailDispatcher`. Mantiene
    la interfaz vieja para back-compat con `services.invitations` y otros
    callers legacy.

    Cada `.send()` adquiere su propia conexión del pool (transaction-
    per-request es el modelo del core). Esto agrega latencia vs pasar
    conn explícito, pero los callers legacy no lo hacen — la latencia es
    asumible para el path de email transaccional (baja-frecuencia).
    """

    name = 'multi-provider'

    def is_real(self) -> bool:
        return True

    async def send(self, message: EmailMessage) -> EmailSendResult:
        from copiloto_core.db.pool import db  # noqa: PLC0415
        from copiloto_core.email import EmailDispatcher  # noqa: PLC0415
        from copiloto_core.email import EmailMessage as NewMessage  # noqa: PLC0415

        new_msg = NewMessage(
            to_address=message.to,
            subject=message.subject,
            html=message.html,
            text=message.text,
            tags=dict(message.tags or {}),
        )
        dispatcher = EmailDispatcher()
        async with db.connection(support_mode=True) as conn:
            result = await dispatcher.send(conn, new_msg, support_mode=False)

        if not result.success:
            # `no_providers_configured` lo manejamos arriba (caller usa
            # NoopProvider en su lugar). Para los demás failures, levantamos
            # `EmailSendError` consistente con el contrato viejo.
            raise EmailSendError(
                result.error or 'email_dispatch_failed',
                status_code=None, body=None,
            )

        return EmailSendResult(
            message_id=result.message_id,
            provider=result.provider_code or self.name,
            delivered_at_provider=True,
        )


class NoopProvider:
    """Loguea el intento pero no manda. Usado cuando no hay providers
    configurados — preserva el comportamiento legacy del core (no se
    rompe el flujo si el operador no configuró nada todavía)."""

    name = 'noop'

    def is_real(self) -> bool:
        return False

    async def send(self, message: EmailMessage) -> EmailSendResult:
        log.info(
            'email.noop.would_send',
            to=_redact_email(message.to),
            subject=message.subject[:80],
            tags=message.tags,
            hint='Sin providers configurados — agregá uno en /admin/platform/email-providers',
        )
        return EmailSendResult(
            message_id='noop-' + _short_id(),
            provider=self.name,
            delivered_at_provider=False,
        )


# ─── Factory ──────────────────────────────────────────────────────────────


# Cache simple — el provider real es el mismo wrapper para todos los
# callers; cuando la lista de providers cambia, el dispatcher la re-fetcha
# de DB en cada send(). No necesitamos invalidar este cache por cambios
# de la tabla.
_cached_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    """Devuelve el provider para mandar emails (compat API vieja).

    En v2.0.0 esto SIEMPRE devuelve el wrapper de `EmailDispatcher`. La
    lógica de "no hay providers" → NoopProvider quedó dentro del
    wrapper: el primer envío que llegue a la DB sin filas devolverá un
    `EmailSendResult(delivered_at_provider=False, provider='noop')` —
    para preservar el comportamiento legacy sin tocar a `invitations.py`.

    Tests que necesitan stubbear el provider pueden monkeypatchear este
    nombre (igual que antes).
    """
    global _cached_provider
    if _cached_provider is None:
        _cached_provider = _DispatcherBackedNoopFallbackProvider()
    return _cached_provider


def clear_email_provider_cache() -> None:
    """Test-only — clearea el wrapper en cache. Reusado en tests."""
    global _cached_provider
    _cached_provider = None


class _DispatcherBackedNoopFallbackProvider:
    """Wrapper que primero intenta `EmailDispatcher`; si devuelve
    `no_providers_configured` cae a NoopProvider sin levantar."""

    name = 'multi-provider'

    def is_real(self) -> bool:
        return True

    async def send(self, message: EmailMessage) -> EmailSendResult:
        from copiloto_core.db.pool import db  # noqa: PLC0415
        from copiloto_core.email import EmailDispatcher  # noqa: PLC0415
        from copiloto_core.email import EmailMessage as NewMessage  # noqa: PLC0415

        new_msg = NewMessage(
            to_address=message.to,
            subject=message.subject,
            html=message.html,
            text=message.text,
            tags=dict(message.tags or {}),
        )
        dispatcher = EmailDispatcher()
        try:
            async with db.connection(support_mode=True) as conn:
                result = await dispatcher.send(conn, new_msg, support_mode=False)
        except Exception as exc:  # noqa: BLE001
            # Si la DB está caída o `app.email_providers` no existe
            # (consumer pre-v2.0.0 que no corrió la migration nueva),
            # caemos a Noop sin crashear el caller. Loguea para
            # diagnóstico.
            log.warning(
                'email.shim.dispatcher_unreachable',
                error=str(exc),
                hint='¿app.email_providers existe? ¿DB up?',
            )
            return await NoopProvider().send(message)

        if not result.success:
            # `no_providers_configured` → NoopProvider (compat con el
            # comportamiento legacy de "sin RESEND_API_KEY = noop").
            if result.error == 'no_providers_configured':
                return await NoopProvider().send(message)
            raise EmailSendError(
                result.error or 'email_dispatch_failed',
            )

        return EmailSendResult(
            message_id=result.message_id,
            provider=result.provider_code or 'multi-provider',
            delivered_at_provider=True,
        )


# ─── Helpers internos ────────────────────────────────────────────────────


def _redact_email(addr: str) -> str:
    """`a***@d.com` para logs PII-safe."""
    if not addr or '@' not in addr:
        return '[invalid]'
    local, _, domain = addr.partition('@')
    if len(local) <= 2:
        masked = '*' * len(local)
    else:
        masked = local[0] + '*' * (len(local) - 2) + local[-1]
    return f'{masked}@{domain}'


def _short_id() -> str:
    import secrets  # noqa: PLC0415
    return secrets.token_hex(8)


__all__ = [
    'EmailMessage',
    'EmailNotConfiguredError',
    'EmailProvider',
    'EmailSendError',
    'EmailSendResult',
    'NoopProvider',
    'clear_email_provider_cache',
    'get_email_provider',
]
