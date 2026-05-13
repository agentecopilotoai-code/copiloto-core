"""TASK-0073 — Catálogo de locales soportados y resolución de strings del bot.

Cada locale ``es-XX`` se modela como un archivo TOML (``app/i18n/es-XX.toml``)
con secciones planas accesibles por ``dot.path`` (e.g. ``greetings.hello``).
La selección del locale por defecto se deriva del ``tenants.country_code`` —
ver ``app.services.locale``.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

_I18N_DIR = Path(__file__).resolve().parent

SUPPORTED_LOCALES: tuple[str, ...] = ('es-CO', 'es-MX', 'es-AR', 'es-CL', 'es-PE', 'es-EC', 'es-UY')


@lru_cache(maxsize=None)
def _load_locale(locale: str) -> dict:
    path = _I18N_DIR / f'{locale}.toml'
    if not path.exists():
        raise FileNotFoundError(f'locale {locale!r} no encontrado en {_I18N_DIR}')
    with path.open('rb') as fh:
        return tomllib.load(fh)


def is_supported(locale: str) -> bool:
    return locale in SUPPORTED_LOCALES


def translate(locale: str, key: str, default: str | None = None) -> str:
    """Devuelve la cadena identificada por ``key`` (``section.field``) para ``locale``.

    Si el locale o la clave no existen, devuelve ``default`` o ``key``.
    """
    if not is_supported(locale):
        return default if default is not None else key
    data: dict | str = _load_locale(locale)
    for part in key.split('.'):
        if not isinstance(data, dict) or part not in data:
            return default if default is not None else key
        data = data[part]
    return data if isinstance(data, str) else (default if default is not None else key)


def list_keys(locale: str) -> list[str]:
    """Aplana las claves del TOML como ``section.field`` para inspección/testing."""

    if not is_supported(locale):
        return []

    flat: list[str] = []

    def _walk(node: dict, prefix: str) -> None:
        for key, value in node.items():
            full = f'{prefix}.{key}' if prefix else key
            if isinstance(value, dict):
                _walk(value, full)
            else:
                flat.append(full)

    _walk(_load_locale(locale), '')
    return sorted(flat)
