"""M45 — cobertura completa de `app.i18n` (antes 0%)."""
from __future__ import annotations

import pytest

from app.i18n import (
    SUPPORTED_LOCALES,
    _load_locale,
    is_supported,
    list_keys,
    translate,
)


# ─── is_supported ──────────────────────────────────────────────────────────


def test_is_supported_known():
    assert is_supported('es-CO') is True
    assert is_supported('es-MX') is True


def test_is_supported_unknown():
    assert is_supported('en-US') is False
    assert is_supported('') is False
    assert is_supported('es-XX') is False


def test_supported_locales_constant_shape():
    # Mantengamos el catálogo en sync con `app.services.locale.SUPPORTED_COUNTRIES`.
    assert isinstance(SUPPORTED_LOCALES, tuple)
    assert len(SUPPORTED_LOCALES) == 7
    for loc in SUPPORTED_LOCALES:
        assert loc.startswith('es-')


# ─── _load_locale ─────────────────────────────────────────────────────────


def test_load_locale_known():
    data = _load_locale('es-CO')
    assert isinstance(data, dict)
    # estructura plana por secciones (greetings, booking, etc.)
    assert 'greetings' in data
    assert isinstance(data['greetings'], dict)


def test_load_locale_missing_raises():
    # invalidamos cache del lru para garantizar la lectura real.
    _load_locale.cache_clear()
    with pytest.raises(FileNotFoundError):
        _load_locale('es-XX')


# ─── translate ─────────────────────────────────────────────────────────────


def test_translate_existing_key():
    out = translate('es-CO', 'greetings.hello')
    assert isinstance(out, str)
    assert out  # non-empty


def test_translate_unsupported_locale_returns_default():
    assert translate('en-US', 'greetings.hello', default='Hi!') == 'Hi!'


def test_translate_unsupported_locale_returns_key_when_no_default():
    assert translate('en-US', 'greetings.hello') == 'greetings.hello'


def test_translate_unknown_key_returns_default():
    assert translate('es-CO', 'nope.does_not_exist', default='nada') == 'nada'


def test_translate_unknown_key_returns_key_when_no_default():
    assert translate('es-CO', 'nope.does_not_exist') == 'nope.does_not_exist'


def test_translate_intermediate_node_returns_default():
    # `greetings` solo existe a nivel sección — `greetings` por sí mismo
    # no es string, debe caer a default/key.
    assert translate('es-CO', 'greetings', default='[section]') == '[section]'


def test_translate_partial_path_no_leaf_string():
    # Camina hasta una clave válida que NO termina en string → fallback.
    assert translate('es-CO', 'greetings.unknown_sub', default='X') == 'X'


# ─── list_keys ─────────────────────────────────────────────────────────────


def test_list_keys_known_locale_returns_sorted():
    keys = list_keys('es-CO')
    assert isinstance(keys, list)
    assert keys == sorted(keys)
    # cada key incluye un `.` (section.field)
    assert all('.' in k for k in keys)


def test_list_keys_unsupported_returns_empty():
    assert list_keys('en-US') == []


def test_list_keys_includes_known_paths():
    keys = list_keys('es-CO')
    # estos viven en el archivo real — si alguien los borra, este test
    # falla y refleja el drift en el catálogo.
    assert 'greetings.hello' in keys
