"""Interfaces abstractas + dataclasses + excepciones del subsistema de email.

Diseñado para espejar `copiloto_core/ai/providers/base.py`:

- ``EmailMessage``: dataclass inmutable con `to_address`, `subject`, `html`,
  `text`, `tags`. Provider-agnostic.
- ``ProviderResult``: dataclass del resultado de un envío. `success` bool,
  `message_id` del provider (si lo dio), `provider_code`, `latency_ms`,
  `error` opcional.
- ``EmailProvider`` ABC: una sola operación, ``send(msg) -> ProviderResult``.
  Cada adapter concreto (Resend, SendGrid, Mailgun, SMTP) la implementa.
- Excepciones tipadas que el dispatcher inspecciona para decidir si
  reintentar con el siguiente provider del chain:
    - ``ProviderUnavailable`` — retryable (5xx, network, key inválida).
    - ``ProviderRateLimited`` — retryable (429 / cuota; opcional retry_after).
    - ``ProviderInvalidConfig`` — NOT retryable (config rota; fallback no
      resuelve el problema).
    - ``ProviderRejected`` — NOT retryable (bad to-addr, dominio no
      verificado; fallback tampoco va a aceptar).

Los adapters DEBEN normalizar errores HTTP/SDK a estas 4 clases — el
dispatcher confía en la clasificación.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ─── Excepciones tipadas ───────────────────────────────────────────────────


class ProviderError(Exception):
    """Base de las excepciones del subsistema de email providers."""


class ProviderUnavailable(ProviderError):
    """El provider está caído / no alcanzable / con key revocada.

    Retryable — el dispatcher intenta con el siguiente del chain (asumiendo
    que el problema es de este provider, no del destinatario).
    """


class ProviderRateLimited(ProviderError):
    """El provider devolvió 429 / cuota excedida.

    Retryable — el dispatcher hace fallback al siguiente. ``retry_after``
    captura el valor del header ``Retry-After`` si el provider lo expone;
    util si en algún futuro queremos backoff antes de reintentar al MISMO
    provider (hoy v2.0.0 hacemos solo fallback inmediato).
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after: float | None = retry_after


class ProviderInvalidConfig(ProviderError):
    """Config del provider rota (e.g. SMTP host no resuelve, JSON inválido).

    NOT retryable — fallback no resuelve el problema (la config la tiene
    que arreglar el platform_owner desde la UI). El dispatcher devuelve
    el error sin probar el siguiente.
    """


class ProviderRejected(ProviderError):
    """El provider rechazó el mensaje por motivo de aplicación.

    Ejemplos: ``to_address`` mal formada, dominio del sender no verificado,
    payload viola las policies del provider. NOT retryable — el siguiente
    provider del chain probablemente rechazaría también.
    """


# ─── DTOs ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmailMessage:
    """Mensaje a enviar — provider-agnostic.

    - ``to_address``: una sola dirección. El dispatcher no soporta
      multi-recipient (cada destinatario debería ser una request separada
      para audit individual + bounce handling per-recipient).
    - ``subject``: línea del asunto. Plain text (los providers escapan).
    - ``html`` / ``text``: cuerpos en ambos formatos. Algunos clients
      legacy solo renderizan ``text``; los modernos prefieren ``html``.
    - ``tags``: metadata para el dashboard del provider (ej.
      ``{'kind': 'invitation', 'tenant': 'acme'}``). Útil para filtrar
      en Resend/SendGrid UI. Optional — pasa ``{}`` si no aplica.
    """
    to_address: str
    subject: str
    html: str
    text: str
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    """Resultado de un envío. El dispatcher lo persiste en
    ``app.email_dispatch_log`` y lo devuelve al caller.

    - ``success=True`` → ``message_id`` puede ser '' si el provider no lo
      expone (raro), pero ``provider_code`` SIEMPRE viene set.
    - ``success=False`` → ``error`` describe el motivo. Convención:
      'no_providers_configured' cuando no hay ninguna fila activa en
      ``app.email_providers``; nombre de la excepción tipada en los
      demás casos.
    - ``latency_ms`` mide el wall-time del último intento exitoso (o del
      último intento fallido si todos fallaron).
    """
    success: bool
    message_id: str = ''
    provider_code: str = ''
    latency_ms: float = 0.0
    error: str | None = None


# ─── Interface abstracta ───────────────────────────────────────────────────


class EmailProvider(ABC):
    """Contrato mínimo de un adapter de email.

    Diseño intencionalmente plano: una operación, sync API para que el
    factory pueda instanciar sin awaitar (la única I/O es leer la
    api_key descifrada de DB, que ya hizo el caller).

    El adapter es responsable de:
      1. Validar su ``config_jsonb`` shape al instanciar (Pydantic
         model). Levanta ``ProviderInvalidConfig`` si está rota.
      2. Mapear errores HTTP / SDK a las 4 excepciones tipadas.
      3. NUNCA logear la api_key (los .repr() de los adapters no la
         exponen).
    """

    #: Identificador legible para audit/logs. Setearlo en __init__ con
    #: el ``code`` único de la fila (e.g. 'resend-main').
    provider_code: str
    #: Tipo (e.g. 'resend'). Útil para métricas por categoría.
    provider_type: str

    @abstractmethod
    async def send(self, msg: EmailMessage) -> ProviderResult:
        """Envía ``msg``. NO debe levantar ``ProviderResult``-success=False;
        en su lugar levanta una de las excepciones tipadas para que el
        dispatcher decida fallback vs propagar.

        Si llega a este método, asume que la config está validada (el
        constructor ya rejected ``ProviderInvalidConfig``).

        Devuelve ``ProviderResult(success=True, ...)`` en path feliz.
        """


__all__ = [
    'EmailMessage',
    'EmailProvider',
    'ProviderError',
    'ProviderInvalidConfig',
    'ProviderRateLimited',
    'ProviderRejected',
    'ProviderResult',
    'ProviderUnavailable',
]
