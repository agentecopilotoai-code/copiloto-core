"""Helper compartido para validar URLs anti-SSRF (audit#2 SEC-019 +
audit#4 SEC-023).

Antes vivía solo en `app/platform_admin/admin_routes.py` como guard al
PATCH de provider config. SEC-023 (audit#4) lo replica en el read-path
del factory de providers (defense-in-depth: si la DB se corrompe o
existe data pre-SEC-019, el factory rechaza al instanciar el adapter).

Reglas (mismo set que admin_routes original):

- Schema: solo `https` para cloud providers; `http`/`https` para
  locales (que pueden apuntar a `http://localhost:11434` o
  `http://sdxl.internal:7860`).
- Host: rechaza `localhost`, `*.local`, `*.internal` SOLO para cloud.
- IPs: rechaza loopback/private/link-local/multicast/reserved/
  unspecified SOLO para cloud.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


# Providers que esperan llegar a una API pública (https con DNS público).
CLOUD_PROVIDERS: frozenset[str] = frozenset(
    {'grok', 'openai', 'anthropic', 'elevenlabs'},
)
# Providers que CORREN localmente — permiten http + IPs privadas /
# hostnames *.local / *.internal por diseño.
LOCAL_PROVIDERS: frozenset[str] = frozenset(
    {'ollama', 'local_sdxl', 'local_whisper'},
)


class UrlSafetyError(ValueError):
    """Levantada cuando la URL viola el contrato anti-SSRF.

    Caller envuelve a `HTTPException` (admin write-path) o
    `ProviderUnavailable` (factory read-path).
    """


def check_provider_url(
    url: str,
    *,
    provider: str,
    field: str = 'url',
    strict: bool | None = None,
) -> None:
    """Valida una URL de provider. Levanta `UrlSafetyError` si es unsafe.

    Args:
      url: la URL completa a validar (e.g. ``https://api.x.ai/v1``).
      provider: nombre del provider (decide si es cloud/local).
      field: nombre del field para el mensaje de error (e.g.
        ``params.base_url``).
      strict: override del mode. ``None`` (default) → cloud si está en
        ``CLOUD_PROVIDERS``, else local. ``True`` fuerza modo estricto
        (cloud) incluso para providers locales (útil cuando un local
        debería apuntar a un host real). ``False`` permite todo lo que
        no sea schema disallowed.

    Raises:
      UrlSafetyError: si la URL viola el contrato.
    """
    if strict is None:
        strict = provider.lower() in CLOUD_PROVIDERS

    parsed = urlparse(url)
    allowed_schemes = ('https',) if strict else ('https', 'http')
    if parsed.scheme not in allowed_schemes:
        raise UrlSafetyError(
            f'{field}: scheme must be one of {allowed_schemes} '
            f'(got {parsed.scheme!r})',
        )
    host = (parsed.hostname or '').lower()
    if not host:
        raise UrlSafetyError(f'{field}: hostname missing')

    if strict and (
        host == 'localhost' or host.endswith(('.local', '.internal'))
    ):
        raise UrlSafetyError(
            f'{field}: hostname {host!r} not allowed for cloud provider',
        )

    # IP-literal check — solo aplica si es estricto (cloud).
    if strict:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return  # DNS hostname — válido para cloud.
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_unspecified or ip.is_reserved):
            raise UrlSafetyError(
                f'{field}: IP {host!r} not allowed for cloud provider '
                f'(private/loopback/link-local/multicast/reserved)',
            )


__all__ = [
    'CLOUD_PROVIDERS',
    'LOCAL_PROVIDERS',
    'UrlSafetyError',
    'check_provider_url',
]
