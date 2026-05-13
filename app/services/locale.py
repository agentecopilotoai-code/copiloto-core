"""TASK-0073 — Resolución de país, locale, moneda, timezone y validación de teléfono.

Cada tenant tiene un ``country_code`` ISO-3166 alfa-2. Desde ese único valor el
producto deriva (cuando no haya override explícito):

* ``locale``   — ``es-XX``
* ``currency`` — ISO-4217 alfa-3
* ``timezone`` — IANA tz
* validación E.164 del teléfono via ``phonenumbers``

Cualquier país no listado aquí se rechaza en la API: el MVP solo vende a los 7
países LatAm soportados.
"""

from __future__ import annotations

import phonenumbers

SUPPORTED_COUNTRIES: tuple[str, ...] = ('CO', 'MX', 'AR', 'CL', 'PE', 'EC', 'UY')

_COUNTRY_PROFILES: dict[str, dict[str, str]] = {
    'CO': {
        'locale': 'es-CO',
        'currency': 'COP',
        'timezone': 'America/Bogota',
        'currency_symbol': '$',
        'thousands_sep': '.',
        'decimal_sep': ',',
        'decimals': '0',
    },
    'MX': {
        'locale': 'es-MX',
        'currency': 'MXN',
        'timezone': 'America/Mexico_City',
        'currency_symbol': '$',
        'thousands_sep': ',',
        'decimal_sep': '.',
        'decimals': '2',
    },
    'AR': {
        'locale': 'es-AR',
        'currency': 'ARS',
        'timezone': 'America/Argentina/Buenos_Aires',
        'currency_symbol': '$',
        'thousands_sep': '.',
        'decimal_sep': ',',
        'decimals': '2',
    },
    'CL': {
        'locale': 'es-CL',
        'currency': 'CLP',
        'timezone': 'America/Santiago',
        'currency_symbol': '$',
        'thousands_sep': '.',
        'decimal_sep': ',',
        'decimals': '0',
    },
    'PE': {
        'locale': 'es-PE',
        'currency': 'PEN',
        'timezone': 'America/Lima',
        'currency_symbol': 'S/',
        'thousands_sep': ',',
        'decimal_sep': '.',
        'decimals': '2',
    },
    'EC': {
        'locale': 'es-EC',
        'currency': 'USD',
        'timezone': 'America/Guayaquil',
        'currency_symbol': '$',
        'thousands_sep': ',',
        'decimal_sep': '.',
        'decimals': '2',
    },
    'UY': {
        'locale': 'es-UY',
        'currency': 'UYU',
        'timezone': 'America/Montevideo',
        'currency_symbol': '$',
        'thousands_sep': '.',
        'decimal_sep': ',',
        'decimals': '2',
    },
}


def is_supported_country(country_code: str | None) -> bool:
    return country_code in SUPPORTED_COUNTRIES


def profile_for(country_code: str) -> dict[str, str]:
    """Devuelve el perfil de país (locale, currency, timezone, formato monetario).

    Lanza ``ValueError`` si el país no está soportado: el MVP no acepta
    países fuera del catálogo y no aplica fallback silencioso.
    """
    if country_code not in _COUNTRY_PROFILES:
        raise ValueError(f'country_code no soportado: {country_code!r}')
    return dict(_COUNTRY_PROFILES[country_code])


def default_locale(country_code: str) -> str:
    return profile_for(country_code)['locale']


def default_currency(country_code: str) -> str:
    return profile_for(country_code)['currency']


def default_timezone(country_code: str) -> str:
    return profile_for(country_code)['timezone']


def format_money(amount: float | int, currency: str) -> str:
    """Formatea ``amount`` en ``currency`` con el estilo del país emisor de esa moneda.

    Acepta cualquier ISO-4217 conocido por el catálogo; si no, cae a un formato
    neutro con coma como separador de miles y dos decimales (``$ 1,500.00 XXX``).
    """
    profile = _profile_by_currency(currency)
    decimals = int(profile['decimals'])
    thousands = profile['thousands_sep']
    decimal = profile['decimal_sep']
    symbol = profile['currency_symbol']
    suffix = currency.upper()

    quantized = round(float(amount), decimals)
    if decimals == 0:
        integer_part = f'{int(quantized):,}'.replace(',', thousands)
        return f'{symbol} {integer_part} {suffix}'
    fmt = f'{{:,.{decimals}f}}'.format(quantized)
    if thousands == '.' and decimal == ',':
        translated = fmt.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
    elif thousands == ',' and decimal == '.':
        translated = fmt
    else:
        translated = fmt.replace(',', '\x00').replace('.', decimal).replace('\x00', thousands)
    return f'{symbol} {translated} {suffix}'


def _profile_by_currency(currency: str) -> dict[str, str]:
    upper = currency.upper()
    for profile in _COUNTRY_PROFILES.values():
        if profile['currency'] == upper:
            return profile
    return {
        'currency': upper,
        'currency_symbol': '$',
        'thousands_sep': ',',
        'decimal_sep': '.',
        'decimals': '2',
    }


class PhoneValidationError(ValueError):
    """El número provisto no se pudo parsear o no es válido para el país."""


def validate_phone(raw: str, country_hint: str | None = None) -> str:
    """Valida y normaliza un teléfono al formato E.164.

    ``country_hint`` es el ``country_code`` ISO-3166 (alfa-2). Si el número ya
    viene en E.164 (``+57…``) el hint es ignorado por ``phonenumbers``. La
    función levanta ``PhoneValidationError`` si el número no parsea o no es
    válido para la región.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PhoneValidationError('teléfono vacío')
    try:
        parsed = phonenumbers.parse(raw, country_hint)
    except phonenumbers.NumberParseException as exc:
        raise PhoneValidationError(f'no se pudo parsear: {exc}') from exc
    if not phonenumbers.is_valid_number(parsed):
        raise PhoneValidationError('número inválido para la región')
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def is_valid_phone(raw: str, country_hint: str | None = None) -> bool:
    try:
        validate_phone(raw, country_hint)
        return True
    except PhoneValidationError:
        return False
