"""SEC-010 (Malformed tenant timezone can disable bot replies) — defienden:

- Schema-level: ``TenantCreate`` y ``TenantUpdate`` (y por herencia
  ``PlatformTenantUpdate``) tienen un ``@field_validator('timezone')`` que
  rechaza valores no-IANA con ``ValidationError`` (FastAPI → 422). Sin esto,
  un PATCH a ``/v1/tenants/{id}`` con ``timezone='America/Bogota/'`` persistía
  el valor inválido.
- Runtime defense en profundidad: ``rag_orchestrator._current_datetime_label``
  y ``digest.safe_zone`` ahora capturan ``ValueError`` y ``TypeError`` además
  de ``ZoneInfoNotFoundError`` — defiende contra valores históricos que ya
  están en la DB y bypassearon el schema (escaparon antes de SEC-010 o
  fueron escritos por migrations / scripts).

Antes del fix: bot dejaba de responder al tenant entero cuando el orchestrator
crasheaba con ``ValueError`` no capturado en ``_current_datetime_label``;
operador necesitaba editar la row a mano para restaurar el servicio.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1 import schemas as v1_schemas
from app.services import digest, rag_orchestrator

SCHEMAS_PATH = Path('app/api/v1/schemas.py')


def _handler_source(module, name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(module, name)))


# ───── Schema validator: TenantCreate / TenantUpdate rechazan inválido ───


def test_tenant_create_rejects_malformed_timezone_with_trailing_slash():
    """Caso histórico del bug: ``'America/Bogota/'`` (trailing slash) es lo
    que un operador podía mandar copiando-pegando de una URL o un CSV con
    artefactos. ``ZoneInfo`` raisea ``ValueError`` (no ``ZoneInfoNotFoundError``)
    para este caso — el validator debe atrapar AMBAS familias."""
    with pytest.raises(ValidationError) as excinfo:
        v1_schemas.TenantCreate(
            slug='test',
            legal_name='Test SAS',
            display_name='Test',
            vertical_code='general',
            timezone='America/Bogota/',
        )
    errors = excinfo.value.errors()
    assert any('timezone' in str(err.get('loc', ())) for err in errors)


def test_tenant_create_rejects_unknown_timezone():
    """``'NotARealZone'`` raisea ``ZoneInfoNotFoundError`` — variante más
    obvia del bug, también debe rechazarse con 422."""
    with pytest.raises(ValidationError):
        v1_schemas.TenantCreate(
            slug='test',
            legal_name='Test SAS',
            display_name='Test',
            vertical_code='general',
            timezone='NotARealZone',
        )


def test_tenant_create_accepts_valid_iana_timezone():
    """Sanity: timezones IANA reales pasan."""
    for tz in ('America/Bogota', 'America/Argentina/Buenos_Aires', 'UTC', 'Europe/Madrid'):
        # No raise.
        v1_schemas.TenantCreate(
            slug='test',
            legal_name='Test SAS',
            display_name='Test',
            vertical_code='general',
            timezone=tz,
        )


def test_tenant_create_accepts_none_timezone():
    """``None`` está OK — el route lo deriva de ``country_code``."""
    instance = v1_schemas.TenantCreate(
        slug='test',
        legal_name='Test SAS',
        display_name='Test',
        vertical_code='general',
        timezone=None,
    )
    assert instance.timezone is None


def test_tenant_update_rejects_malformed_timezone():
    """``TenantUpdate`` se usa en PATCH ``/v1/tenants/{id}`` — la ruta más
    común de inyección de timezones inválidos en producción."""
    with pytest.raises(ValidationError):
        v1_schemas.TenantUpdate(timezone='America/Bogota/')


def test_tenant_update_rejects_non_string_timezone():
    """Defense en profundidad: si el JSON manda ``"timezone": 123``, sin
    chequeo de tipo el validator crashearía con ``TypeError`` confuso
    dentro de ``ZoneInfo()`` y FastAPI lo expondría como 500. Ahora se
    rechaza con 422 explícito."""
    with pytest.raises(ValidationError):
        v1_schemas.TenantUpdate(timezone=123)  # type: ignore[arg-type]


def test_tenant_update_accepts_valid_timezone():
    instance = v1_schemas.TenantUpdate(timezone='America/Argentina/Buenos_Aires')
    assert instance.timezone == 'America/Argentina/Buenos_Aires'


def test_platform_tenant_update_inherits_timezone_validator():
    """``PlatformTenantUpdate`` extiende ``TenantUpdate`` y debe heredar el
    validator. Sin esto, un platform_owner podría bypassear el guard
    PATCH-eando vía el endpoint de platform admin."""
    with pytest.raises(ValidationError):
        v1_schemas.PlatformTenantUpdate(timezone='Mars/Olympus_Mons')


# ───── Helper de validación expone la firma esperada ─────────────────────


def test_validate_iana_timezone_helper_exists():
    """Ancla el helper compartido en el módulo; si alguien lo borra
    pensando que es legacy, este test falla."""
    assert hasattr(v1_schemas, '_validate_iana_timezone')


def test_validate_iana_timezone_passes_none_and_empty():
    """None y '' son válidos — corresponden a "usar default del tenant"."""
    assert v1_schemas._validate_iana_timezone(None) is None
    assert v1_schemas._validate_iana_timezone('') == ''


def test_validate_iana_timezone_catches_all_zoneinfo_exceptions():
    """El validator debe capturar la unión completa de excepciones que
    ZoneInfo levanta — ZoneInfoNotFoundError, ValueError, KeyError,
    TypeError — porque cada CPython release / cada input mal formado
    surface una distinta."""
    src = _handler_source(v1_schemas, '_validate_iana_timezone')
    # Las cuatro deben aparecer en el except.
    assert 'ZoneInfoNotFoundError' in src
    assert 'ValueError' in src
    assert 'KeyError' in src
    assert 'TypeError' in src


# ───── Runtime defense: rag_orchestrator y digest catch ampliado ─────────


def test_rag_orchestrator_catches_value_error_not_just_zoneinfo_not_found():
    """Path central del bug — sin este catch, un timezone histórico mal
    formado tumba ``_current_datetime_label`` y el bot deja de responder
    al tenant entero. El except debe atrapar al menos ZoneInfoNotFoundError
    + ValueError + TypeError."""
    src = _handler_source(rag_orchestrator, '_current_datetime_label')
    # Busca la línea del except.
    assert 'ZoneInfoNotFoundError' in src
    assert 'ValueError' in src
    assert 'TypeError' in src


def test_rag_orchestrator_logs_invalid_timezone_for_observability():
    """Cuando cae al fallback, debe loguearse — el operador necesita ver
    qué tenant tiene la row mal seteada para arreglarla a mano."""
    src = _handler_source(rag_orchestrator, '_current_datetime_label')
    assert 'log.warning(' in src
    assert "'rag_orchestrator.invalid_timezone'" in src


def test_rag_orchestrator_falls_back_to_default_tz():
    """Comportamiento de fallback: el handler NO debe re-raise; debe
    seguir y devolver un label válido con la default."""
    src = _handler_source(rag_orchestrator, '_current_datetime_label')
    assert "ZoneInfo('America/Bogota')" in src
    # No re-raise dentro del except.
    assert 'raise' not in src.split('except')[1].split('\n', 5)[0]


def test_rag_orchestrator_actually_recovers_on_bad_timezone():
    """Test dinámico: pasar inputs malos NO debe raise."""
    # ValueError-triggering input.
    label1, used1 = rag_orchestrator._current_datetime_label('America/Bogota/')
    assert used1 == 'America/Bogota'  # fallback
    assert isinstance(label1, str) and len(label1) > 0
    # ZoneInfoNotFoundError-triggering input.
    label2, used2 = rag_orchestrator._current_datetime_label('NotARealZone')
    assert used2 == 'America/Bogota'
    # Empty input → empty triggers `or 'America/Bogota'` early.
    label3, used3 = rag_orchestrator._current_datetime_label('')
    assert used3 == 'America/Bogota'
    assert isinstance(label3, str)


def test_digest_safe_zone_catches_value_error():
    """Mismo gap en el digest worker — ZoneInfo crashea con ValueError
    para trailing slash; el worker debe seguir corriendo (fallback UTC)."""
    src = _handler_source(digest, 'safe_zone')
    assert 'ZoneInfoNotFoundError' in src
    assert 'ValueError' in src
    assert 'TypeError' in src


def test_digest_safe_zone_actually_recovers_on_bad_timezone():
    """Dinámico: digest worker no se cae con TZ malo."""
    from zoneinfo import ZoneInfo
    # Cada input debe devolver un ZoneInfo válido (UTC fallback).
    for bad in ('America/Bogota/', 'NotARealZone', '', None):
        tz = digest.safe_zone(bad)
        assert tz is not None
    # Casos sanos siguen funcionando.
    tz = digest.safe_zone('America/Bogota')
    assert tz == ZoneInfo('America/Bogota')


# ───── Schemas.py declara `field_validator` (no podemos perderlo) ────────


def test_schemas_uses_field_validator_for_timezone():
    """AST-anchor: si alguien refactoriza y olvida el `@field_validator`,
    el bug regresa. Verifica que la decoración existe en TENANT_UPDATE
    y TENANT_CREATE."""
    src = SCHEMAS_PATH.read_text()
    assert "@field_validator('timezone')" in src
    # Debe aparecer al menos 2 veces (TenantCreate + TenantUpdate).
    assert src.count("@field_validator('timezone')") >= 2
