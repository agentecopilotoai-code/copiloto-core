"""Adapter de email para SMTP genérico (vía ``aiosmtplib``).

Config requerida (validada por Pydantic al instanciar):
  - ``host``: hostname del servidor SMTP (e.g. 'smtp.gmail.com').
  - ``port``: típicamente 587 (STARTTLS), 465 (TLS implícito), 25 (clear).
  - ``username``: cuenta de auth (la password viaja como api_key cifrado).
  - ``use_tls``: si True, hace STARTTLS sobre el puerto. Para 465 usar
    False (TLS implícito) + cliente que sepa wrappear el socket; hoy
    aiosmtplib lo decide por el flag `use_tls=True` (TLS desde el
    handshake) vs `start_tls=True` (STARTTLS post-EHLO).

Notas de seguridad:
  - Nunca aceptamos SMTP plaintext en producción — si `use_tls=false`
    Y el host no es ``localhost`` el adapter levanta InvalidConfig.
  - Username/password se cifran como api_key (Fernet) en DB. El SMTP
    típico recibe la password en api_key; el username vive en config.
"""
from __future__ import annotations

import asyncio
import time
from email.message import EmailMessage as StdEmailMessage

from pydantic import BaseModel, ConfigDict, Field

from copiloto_core.email.providers.base import (
    EmailMessage,
    EmailProvider,
    ProviderInvalidConfig,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)


class _SmtpConfig(BaseModel):
    """Shape del `config_jsonb` para SMTP. `extra='forbid'` para typos."""
    model_config = ConfigDict(extra='forbid')
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    use_tls: bool = True


class SMTPProvider(EmailProvider):
    """Adapter SMTP genérico — útil para Gmail, Postfix on-prem, AWS SES SMTP."""

    provider_type = 'smtp'

    def __init__(
        self,
        *,
        provider_code: str,
        api_key: str,
        config: dict,
        from_address: str,
        from_name: str,
    ) -> None:
        try:
            parsed = _SmtpConfig.model_validate(config or {})
        except Exception as exc:
            raise ProviderInvalidConfig(
                f'smtp config invalid: {exc}'
            ) from exc
        # api_key = password SMTP. Vacío sí está permitido solo para
        # `localhost` (open relay de dev); en producción rechazamos.
        if not from_address:
            raise ProviderInvalidConfig('smtp: from_address vacío')
        if not parsed.use_tls and parsed.host not in ('localhost', '127.0.0.1', '::1'):
            raise ProviderInvalidConfig(
                'smtp: use_tls=false solo permitido para localhost'
            )
        if not api_key and parsed.host not in ('localhost', '127.0.0.1', '::1'):
            raise ProviderInvalidConfig(
                'smtp: api_key (password) requerido para hosts remotos'
            )
        self.provider_code = provider_code
        self._password = api_key
        self._host = parsed.host
        self._port = parsed.port
        self._username = parsed.username
        self._use_tls = parsed.use_tls
        self._from_address = from_address
        self._from_name = from_name

    async def send(self, msg: EmailMessage) -> ProviderResult:
        # Construir el mensaje MIME con multipart/alternative (text + html).
        # `EmailMessage` de stdlib hace todo el escapado y headers.
        std_msg = StdEmailMessage()
        std_msg['Subject'] = msg.subject
        std_msg['From'] = (
            f'{self._from_name} <{self._from_address}>'
            if self._from_name else self._from_address
        )
        std_msg['To'] = msg.to_address
        std_msg.set_content(msg.text)
        std_msg.add_alternative(msg.html, subtype='html')
        if msg.tags:
            # SMTP no tiene "tags" estandarizadas; reusamos `X-Tag` por
            # convención (Postfix/SES lo mantienen como custom header).
            for k, v in msg.tags.items():
                std_msg[f'X-Tag-{k}'] = v

        # Lazy import — aiosmtplib es opt-in dep (no cargada en tests que
        # no tocan SMTP). Si falta, el adapter falla con mensaje claro.
        try:
            import aiosmtplib  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailable(
                'aiosmtplib no instalado — pip install aiosmtplib'
            ) from exc

        t0 = time.monotonic()
        try:
            # `start_tls` es STARTTLS sobre el puerto plano (típicamente
            # 587). Para TLS implícito (465) sería `use_tls=True` + sin
            # `start_tls`. Por simplicidad usamos solo STARTTLS — el
            # operador que necesite 465 puede agregar el branch.
            await aiosmtplib.send(
                std_msg,
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
                start_tls=self._use_tls,
                timeout=15.0,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderUnavailable(
                f'smtp timeout connecting to {self._host}:{self._port}'
            ) from exc
        except aiosmtplib.SMTPAuthenticationError as exc:
            # Auth real fail (user/pass). Retryable hacia otro provider.
            raise ProviderUnavailable(
                f'smtp auth failed for {self._username}@{self._host}: {exc}'
            ) from exc
        except aiosmtplib.SMTPRecipientsRefused as exc:
            raise ProviderRejected(
                f'smtp recipient refused: {exc}'
            ) from exc
        except aiosmtplib.SMTPSenderRefused as exc:
            raise ProviderRejected(
                f'smtp sender refused: {exc}'
            ) from exc
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise ProviderUnavailable(
                f'smtp error: {type(exc).__name__}: {exc}'
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000.0
        # SMTP no devuelve un message_id explícito — reusamos el
        # `Message-ID` del header (lo setea Python automáticamente al
        # serializar el mensaje).
        message_id = std_msg.get('Message-ID', '') or ''
        return ProviderResult(
            success=True,
            message_id=message_id,
            provider_code=self.provider_code,
            latency_ms=latency_ms,
        )


__all__ = ['SMTPProvider']
