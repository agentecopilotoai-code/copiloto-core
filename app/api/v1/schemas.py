"""Schemas Pydantic transversales del core.

Solo contiene los schemas usados por los handlers del core (TenantCreate,
TenantUpdate, PlatformTenantUpdate). Los módulos opt-in declaran sus
propios schemas en su feature folder.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.locale import SUPPORTED_COUNTRIES

# Solo vendemos a 7 países LatAm. Patrón viene del catálogo autoritativo
# de `app.services.locale` para evitar drift.
SUPPORTED_COUNTRY_PATTERN = '^(' + '|'.join(SUPPORTED_COUNTRIES) + ')$'

# M23 — slug acotado a `[a-z0-9-]`, no empieza ni termina en `-`, longitud
# 2..63 (encaja en hostname segment / path segment URL-safe sin necesidad
# de encoding). Bloquea inyección de path traversal en URLs públicas como
# `/admin/tenant/{slug}/...` y evita drift con el constraint del frontend
# (`admin-panel/.../resolveSafeHomeModule.js`).
TENANT_SLUG_PATTERN = r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'


def _validate_iana_timezone(value: str | None) -> str | None:
    """SEC-010 — reject malformed timezones at the API boundary.

    Sin este validator, un admin podría PATCH `timezone` a basura como
    ``"America/Bogota/"`` o ``"NotARealZone"``, que persistiría y luego
    rompería cualquier ``ZoneInfo(value)`` aguas abajo.

    Acepta ``None`` / empty (default de columna). Valida strings reales
    con ``ZoneInfo(value)``; captura ``ZoneInfoNotFoundError``,
    ``ValueError``, ``KeyError``, ``TypeError``. Pydantic convierte el
    ``ValueError`` levantado en ``ValidationError`` → 422.
    """
    if value is None or value == '':
        return value
    if not isinstance(value, str):
        raise ValueError('timezone must be a string')
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f'Invalid IANA timezone: {value!r}') from exc
    return value


class TenantCreate(BaseModel):
    # M21 — `extra='forbid'` cierra el contrato: si el frontend manda un
    # campo desconocido (typo, drift), Pydantic devuelve 422 en lugar de
    # silenciarlo (que oculta bugs aguas arriba).
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    slug: str = Field(min_length=2, max_length=63, pattern=TENANT_SLUG_PATTERN)
    legal_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    vertical_code: str = Field(min_length=1, max_length=64)
    business_type_label: str | None = Field(default=None, min_length=1, max_length=160)
    country_code: str = Field(default='CO', pattern=SUPPORTED_COUNTRY_PATTERN)
    # Si ``timezone`` viene vacío, el route lo deriva de ``country_code`` vía
    # ``app.services.locale.default_timezone``.
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator('timezone')
    @classmethod
    def _validate_timezone_field(cls, v: str | None) -> str | None:
        return _validate_iana_timezone(v)


class TenantUpdate(BaseModel):
    """Fields a tenant admin may patch on their own tenant.

    ``status`` está intencionalmente excluido — lifecycle transitions
    (trial → active → suspended → churned) son del platform_owner y viven
    en :class:`PlatformTenantUpdate`.
    """

    # M21 — extra=forbid: el PATCH explícitamente lista los campos
    # mutables; cualquier otro es rechazado con 422.
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    slug: str | None = Field(default=None, min_length=2, max_length=63, pattern=TENANT_SLUG_PATTERN)
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    vertical_code: str | None = Field(default=None, min_length=1, max_length=64)
    business_type_label: str | None = Field(default=None, min_length=1, max_length=160)
    country_code: str | None = Field(default=None, pattern=SUPPORTED_COUNTRY_PATTERN)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator('timezone')
    @classmethod
    def _validate_timezone_field(cls, v: str | None) -> str | None:
        return _validate_iana_timezone(v)


class PlatformTenantUpdate(TenantUpdate):
    """Superset de :class:`TenantUpdate` que también puede escribir ``status``.

    Solo handlers del `platform_admin_router` deben aceptar este schema.
    """

    status: str | None = Field(default=None, pattern='^(trial|active|suspended|churned)$')


__all__ = [
    'PlatformTenantUpdate',
    'SUPPORTED_COUNTRY_PATTERN',
    'TENANT_SLUG_PATTERN',
    'TenantCreate',
    'TenantUpdate',
]
