"""Tests for `app/services/locale.py`."""
from __future__ import annotations

import pytest


# ───── is_supported_country ──────────────────────────────────────────────


def test_is_supported_country_true():
    from copiloto_core.services.locale import is_supported_country
    for code in ('CO', 'MX', 'AR', 'CL', 'PE', 'EC', 'UY'):
        assert is_supported_country(code) is True


def test_is_supported_country_false():
    from copiloto_core.services.locale import is_supported_country
    assert is_supported_country('US') is False
    assert is_supported_country('BR') is False
    assert is_supported_country('') is False
    assert is_supported_country(None) is False


# ───── profile_for ───────────────────────────────────────────────────────


def test_profile_for_returns_full_profile():
    from copiloto_core.services.locale import profile_for
    co = profile_for('CO')
    assert co['locale'] == 'es-CO'
    assert co['currency'] == 'COP'
    assert co['timezone'] == 'America/Bogota'
    assert co['decimals'] == '0'


def test_profile_for_each_country():
    from copiloto_core.services.locale import SUPPORTED_COUNTRIES, profile_for
    for code in SUPPORTED_COUNTRIES:
        p = profile_for(code)
        assert 'locale' in p
        assert 'currency' in p
        assert 'timezone' in p


def test_profile_for_unsupported_raises():
    from copiloto_core.services.locale import profile_for
    with pytest.raises(ValueError, match='no soportado'):
        profile_for('US')


def test_profile_for_returns_copy():
    """Calling profile_for twice returns different dict instances."""
    from copiloto_core.services.locale import profile_for
    p1 = profile_for('CO')
    p1['locale'] = 'mutated'
    p2 = profile_for('CO')
    assert p2['locale'] == 'es-CO'


# ───── default_locale / default_currency / default_timezone ──────────────


def test_default_locale():
    from copiloto_core.services.locale import default_locale
    assert default_locale('CO') == 'es-CO'
    assert default_locale('MX') == 'es-MX'


def test_default_currency():
    from copiloto_core.services.locale import default_currency
    assert default_currency('CO') == 'COP'
    assert default_currency('EC') == 'USD'


def test_default_timezone():
    from copiloto_core.services.locale import default_timezone
    assert default_timezone('AR') == 'America/Argentina/Buenos_Aires'
    assert default_timezone('UY') == 'America/Montevideo'


# ───── format_money ──────────────────────────────────────────────────────


def test_format_money_cop_no_decimals():
    from copiloto_core.services.locale import format_money
    out = format_money(50000, 'COP')
    assert '50.000' in out  # COP uses '.' as thousands sep
    assert 'COP' in out
    assert '$' in out


def test_format_money_mxn_with_decimals():
    from copiloto_core.services.locale import format_money
    out = format_money(1500.5, 'MXN')
    assert '1,500.50' in out  # MXN uses ',' thousands and '.' decimal
    assert 'MXN' in out


def test_format_money_clp_no_decimals():
    from copiloto_core.services.locale import format_money
    out = format_money(123456, 'CLP')
    assert '123.456' in out
    assert 'CLP' in out


def test_format_money_pen_uses_S_slash_symbol():
    from copiloto_core.services.locale import format_money
    out = format_money(100, 'PEN')
    assert 'S/' in out
    assert 'PEN' in out


def test_format_money_unknown_currency_falls_back():
    from copiloto_core.services.locale import format_money
    out = format_money(1500.5, 'BRL')
    # Default profile: $ symbol, 2 decimals, ',' thousands, '.' decimal
    assert 'BRL' in out
    assert '1,500.50' in out


def test_format_money_integer_zero():
    from copiloto_core.services.locale import format_money
    out = format_money(0, 'COP')
    assert 'COP' in out
    assert '0' in out


def test_format_money_argentine_uses_dot_thousands_comma_decimal():
    from copiloto_core.services.locale import format_money
    out = format_money(1234.5, 'ARS')
    # AR: '.' thousands, ',' decimal, 2 decimals
    assert '1.234,50' in out


# ───── validate_phone / is_valid_phone ──────────────────────────────────


def test_validate_phone_returns_e164():
    from copiloto_core.services.locale import validate_phone
    out = validate_phone('300 555 1212', 'CO')
    assert out.startswith('+57')


def test_validate_phone_e164_input():
    from copiloto_core.services.locale import validate_phone
    # If already E.164, country hint ignored
    out = validate_phone('+573005551212', None)
    assert out == '+573005551212'


def test_validate_phone_invalid_raises():
    from copiloto_core.services.locale import PhoneValidationError, validate_phone
    with pytest.raises(PhoneValidationError, match='inválido'):
        validate_phone('123', 'CO')


def test_validate_phone_unparseable_raises():
    from copiloto_core.services.locale import PhoneValidationError, validate_phone
    with pytest.raises(PhoneValidationError, match='parsear'):
        validate_phone('garbage', None)


def test_validate_phone_empty_raises():
    from copiloto_core.services.locale import PhoneValidationError, validate_phone
    with pytest.raises(PhoneValidationError, match='vac'):
        validate_phone('', 'CO')
    with pytest.raises(PhoneValidationError):
        validate_phone('   ', 'CO')


def test_validate_phone_non_string_raises():
    from copiloto_core.services.locale import PhoneValidationError, validate_phone
    with pytest.raises(PhoneValidationError):
        validate_phone(None, 'CO')


def test_is_valid_phone_true():
    from copiloto_core.services.locale import is_valid_phone
    assert is_valid_phone('+573005551212') is True


def test_is_valid_phone_false():
    from copiloto_core.services.locale import is_valid_phone
    assert is_valid_phone('garbage') is False
    assert is_valid_phone('') is False


# ───── SUPPORTED_USER_LOCALES ─────────────────────────────────────────────


def test_supported_user_locales_includes_alternates():
    """BUG-075: SUPPORTED_USER_LOCALES extends past country defaults."""
    from copiloto_core.services.locale import SUPPORTED_USER_LOCALES
    assert 'es-CO' in SUPPORTED_USER_LOCALES
    assert 'es-ES' in SUPPORTED_USER_LOCALES
    assert 'en-US' in SUPPORTED_USER_LOCALES
    assert 'pt-BR' in SUPPORTED_USER_LOCALES
