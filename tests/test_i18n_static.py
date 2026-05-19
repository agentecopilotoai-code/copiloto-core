"""Static tests for TASK-0073 — i18n multi-país.

Cubre:
- ``app.services.locale`` resuelve correctamente locale / currency / timezone
  por país (CO, MX, AR, CL, PE, EC, UY).
- ``format_money`` produce el formato esperado por país (separadores y símbolo).
- ``validate_phone`` acepta números válidos por país y rechaza basura.
- ``app.i18n`` carga los TOML para los locales soportados y resuelve claves
  jerárquicas (``greetings.hello``, ``booking.ask_service``, etc.).
- Schemas Pydantic rechazan ``country_code`` fuera del catálogo.
- Esquema SQL declara ``tenant_settings.currency`` y el ``check`` de país en
  ``tenants.country_code``.
- Route ``create_tenant`` deriva timezone/locale/currency del país.
- Admin Panel ``TenantSetupWizard.jsx`` expone el selector con los 7 países.

Mínimo ≥10 asserts por país soportado.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api.v1 import schemas
from app.i18n import SUPPORTED_LOCALES, is_supported, list_keys, translate
from app.services.locale import (
    SUPPORTED_COUNTRIES,
    PhoneValidationError,
    default_currency,
    default_locale,
    default_timezone,
    format_money,
    is_supported_country,
    is_valid_phone,
    profile_for,
    validate_phone,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TENANT_SETUP_FEATURE = REPO_ROOT / 'admin-panel' / 'src' / 'features' / 'owner-admin' / 'tenant-setup'


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))


# ── Catálogos -----------------------------------------------------------------

def test_supported_countries_catalog_is_exact():
    """El MVP soporta exactamente 7 países LatAm."""
    assert SUPPORTED_COUNTRIES == ('CO', 'MX', 'AR', 'CL', 'PE', 'EC', 'UY')


def test_supported_locales_match_countries():
    """Cada país tiene su locale ``es-XX`` en ``app.i18n``."""
    expected = {f'es-{c}' for c in SUPPORTED_COUNTRIES}
    assert set(SUPPORTED_LOCALES) == expected


def test_profile_for_rejects_unsupported_country():
    with pytest.raises(ValueError):
        profile_for('US')
    with pytest.raises(ValueError):
        profile_for('BR')


def test_is_supported_country_predicate():
    assert is_supported_country('CO') is True
    assert is_supported_country('MX') is True
    assert is_supported_country('BR') is False
    assert is_supported_country(None) is False


# ── Helpers para barrer los 7 países ------------------------------------------

@pytest.mark.parametrize('country', SUPPORTED_COUNTRIES)
def test_profile_contains_mandatory_fields(country):
    """Cada profile debe traer locale/currency/timezone y datos de formato."""
    profile = profile_for(country)
    required = {'locale', 'currency', 'timezone', 'currency_symbol', 'thousands_sep', 'decimal_sep', 'decimals'}
    assert required.issubset(profile.keys())
    assert profile['locale'] == f'es-{country}'
    assert len(profile['currency']) == 3
    assert profile['timezone'].startswith('America/')


# ── Por país: 10+ asserts cada uno --------------------------------------------

def _assert_country_profile(country, expected_locale, expected_currency, tz_keyword,
                            expected_format, phone_raw, phone_e164):
    """Helper que ejecuta los ≥10 asserts pedidos por la tarea."""
    profile = profile_for(country)
    # 1-3: locale / currency / timezone derivados
    assert default_locale(country) == expected_locale
    assert default_currency(country) == expected_currency
    assert tz_keyword in default_timezone(country)
    # 4: el profile y los defaults son consistentes
    assert profile['locale'] == expected_locale and profile['currency'] == expected_currency
    # 5: formato de moneda 1500
    assert format_money(1500, expected_currency) == expected_format
    # 6: format_money es estable para floats con la misma magnitud
    assert format_money(1500.0, expected_currency) == expected_format
    # 7: TOML del locale existe
    assert (REPO_ROOT / 'app' / 'i18n' / f'{expected_locale}.toml').exists()
    # 8: i18n.translate resuelve clave jerárquica
    greeting = translate(expected_locale, 'greetings.hello')
    assert greeting and greeting != 'greetings.hello'
    # 9: el TOML expone secciones mínimas
    keys = list_keys(expected_locale)
    for required in ('greetings.hello', 'booking.ask_service', 'fallback.out_of_scope',
                     'currency.suffix'):
        assert required in keys
    # 10: phonenumbers acepta un E.164 válido del país
    assert validate_phone(phone_raw, country) == phone_e164
    # 11: rechazo de teléfono inválido
    with pytest.raises(PhoneValidationError):
        validate_phone('not-a-phone', country)
    # 12: schema Pydantic acepta el country_code
    schemas.TenantCreate(
        slug='x', legal_name='X', display_name='X',
        vertical_code='gym', country_code=country,
    )


def test_country_profile_CO():
    _assert_country_profile(
        country='CO',
        expected_locale='es-CO',
        expected_currency='COP',
        tz_keyword='Bogota',
        expected_format='$ 1.500 COP',
        phone_raw='+57 300 123 4567',
        phone_e164='+573001234567',
    )


def test_country_profile_MX():
    _assert_country_profile(
        country='MX',
        expected_locale='es-MX',
        expected_currency='MXN',
        tz_keyword='Mexico_City',
        expected_format='$ 1,500.00 MXN',
        phone_raw='+52 55 1234 5678',
        phone_e164='+525512345678',
    )


def test_country_profile_AR():
    _assert_country_profile(
        country='AR',
        expected_locale='es-AR',
        expected_currency='ARS',
        tz_keyword='Buenos_Aires',
        expected_format='$ 1.500,00 ARS',
        phone_raw='+54 11 4321 5678',
        phone_e164='+541143215678',
    )


def test_country_profile_CL():
    _assert_country_profile(
        country='CL',
        expected_locale='es-CL',
        expected_currency='CLP',
        tz_keyword='Santiago',
        expected_format='$ 1.500 CLP',
        phone_raw='+56 9 5555 0000',
        phone_e164='+56955550000',
    )


def test_country_profile_PE():
    _assert_country_profile(
        country='PE',
        expected_locale='es-PE',
        expected_currency='PEN',
        tz_keyword='Lima',
        expected_format='S/ 1,500.00 PEN',
        phone_raw='+51 999 123 456',
        phone_e164='+51999123456',
    )


def test_country_profile_EC():
    _assert_country_profile(
        country='EC',
        expected_locale='es-EC',
        expected_currency='USD',
        tz_keyword='Guayaquil',
        expected_format='$ 1,500.00 USD',
        phone_raw='+593 99 123 4567',
        phone_e164='+593991234567',
    )


def test_country_profile_UY():
    _assert_country_profile(
        country='UY',
        expected_locale='es-UY',
        expected_currency='UYU',
        tz_keyword='Montevideo',
        expected_format='$ 1.500,00 UYU',
        phone_raw='+598 99 123 456',
        phone_e164='+59899123456',
    )


# ── Phone validator detalle ---------------------------------------------------

def test_validate_phone_rejects_wrong_country_hint():
    """Un E.164 de México con hint AR sigue siendo válido porque viaja en E.164,
    pero un nacional sin ``+`` y con hint equivocado debe rechazarse."""
    with pytest.raises(PhoneValidationError):
        validate_phone('5512345678', 'AR')
    # El mismo nacional con el hint correcto sí parsea.
    assert validate_phone('5512345678', 'MX') == '+525512345678'


def test_is_valid_phone_wrapper():
    assert is_valid_phone('+52 55 1234 5678', 'MX') is True
    assert is_valid_phone('', 'MX') is False


def test_validate_phone_rejects_empty():
    with pytest.raises(PhoneValidationError):
        validate_phone('   ', 'CO')


# ── Formateo monetario en casos límite ----------------------------------------

def test_format_money_keeps_thousands_per_country():
    assert format_money(1234567, 'COP') == '$ 1.234.567 COP'
    assert format_money(1234567, 'MXN') == '$ 1,234,567.00 MXN'
    assert format_money(1234567, 'ARS') == '$ 1.234.567,00 ARS'


def test_format_money_unknown_currency_falls_back_to_neutral():
    """Una moneda no listada usa formato neutro estilo MX (comas/punto)."""
    assert format_money(1500, 'BRL') == '$ 1,500.00 BRL'


# ── Schemas / contratos -------------------------------------------------------

def test_tenant_create_rejects_country_outside_catalog():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        schemas.TenantCreate(
            slug='x', legal_name='X', display_name='X',
            vertical_code='gym', country_code='US',
        )


def test_tenant_create_timezone_is_optional_for_country_derivation():
    """Si no se envía ``timezone`` el route lo derivará; el schema lo permite."""
    payload = schemas.TenantCreate(
        slug='x', legal_name='X', display_name='X',
        vertical_code='gym', country_code='MX',
    )
    assert payload.timezone is None


def test_supported_country_pattern_matches_catalog():
    """El patrón regex viene del mismo catálogo que ``locale_service``."""
    pattern = schemas.SUPPORTED_COUNTRY_PATTERN
    for code in SUPPORTED_COUNTRIES:
        assert code in pattern
    assert 'US' not in pattern


# ── SQL ----------------------------------------------------------------------

def test_schema_declares_currency_column_on_tenant_settings():
    sql = (REPO_ROOT / 'infra' / 'postgres' / '01-schema.sql').read_text()
    assert 'currency char(3) not null default \'COP\'' in sql


def test_schema_constraints_country_code_to_supported_list():
    sql = (REPO_ROOT / 'infra' / 'postgres' / '01-schema.sql').read_text()
    assert "country_code in ('CO','MX','AR','CL','PE','EC','UY')" in sql


# ── i18n loader --------------------------------------------------------------

def test_i18n_loader_returns_default_for_unknown_locale():
    assert is_supported('en-US') is False
    assert translate('en-US', 'greetings.hello', 'fallback') == 'fallback'
    assert translate('en-US', 'greetings.hello') == 'greetings.hello'


def test_i18n_loader_returns_key_for_unknown_section():
    assert translate('es-CO', 'no.section.here') == 'no.section.here'


# ── Route wiring -------------------------------------------------------------

def test_routes_derive_country_profile_in_create_tenant():
    """``create_tenant`` debe consultar el profile del país para derivar tz/locale/currency."""
    # After the routes.py refactor (phase 3) the platform_admin handlers
    # live in app/api/v1/handlers/platform_admin_handlers.py — use the
    # aggregated source so the asserts keep matching regardless of file
    # boundaries.
    from tests._routes_aggregator import routes_aggregated_source

    routes_src = routes_aggregated_source()
    assert 'locale_service.profile_for(payload.country_code)' in routes_src
    # Se pasa locale y currency al insert de tenant_settings.
    assert "insert into app.tenant_settings (tenant_id, escalation_policy, locale, currency)" in routes_src


def test_digest_worker_reads_currency_from_settings():
    """El digest dejó de derivar la moneda del locale: la lee de la columna."""
    worker_src = (REPO_ROOT / 'app' / 'workers' / 'digest_worker.py').read_text()
    assert 'ts.currency' in worker_src
    assert '_currency_for_locale' not in worker_src


# ── Admin Panel --------------------------------------------------------------

def test_admin_panel_wizard_exposes_country_catalog():
    wizard_src = _tenant_setup_source()
    # Catálogo definido en el componente.
    for code in SUPPORTED_COUNTRIES:
        assert f"{code}: {{" in wizard_src
    assert 'COUNTRY_PROFILES' in wizard_src
    assert "SUPPORTED_COUNTRIES = ['CO'," in wizard_src
    # Selector reemplazó al input libre. UI-021 movió el <select> a
    # GeneralTab.jsx envuelto en <FormField>, sumando 2 niveles de
    # indentación respecto del wizard original.
    assert '<select\n              value={tenantForm.country_code}' in wizard_src


# ── pyproject -----------------------------------------------------------------

def test_pyproject_pins_phonenumbers_dependency():
    pyproject = (REPO_ROOT / 'pyproject.toml').read_text()
    assert 'phonenumbers==' in pyproject


# ── Sanity de format_money por moneda -----------------------------------------

@pytest.mark.parametrize('amount,currency,expected', [
    (0, 'COP', '$ 0 COP'),
    (0, 'MXN', '$ 0.00 MXN'),
    (250, 'PEN', 'S/ 250.00 PEN'),
    (1.5, 'USD', '$ 1.50 USD'),
    (1999, 'CLP', '$ 1.999 CLP'),
    (1999.99, 'UYU', '$ 1.999,99 UYU'),
    (1234.5, 'ARS', '$ 1.234,50 ARS'),
])
def test_format_money_examples(amount, currency, expected):
    assert format_money(amount, currency) == expected
