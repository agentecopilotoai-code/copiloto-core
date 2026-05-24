"""Tests para helper de código de verificación."""
from __future__ import annotations

import pytest

from app.gd.services.codigo_verificacion import (
    LONGITUD_CODIGO, _ALFABETO_SEGURO,
    es_codigo_valido, generar_codigo_verificacion,
)


class TestGenerar:
    def test_longitud_default(self) -> None:
        c = generar_codigo_verificacion()
        assert len(c) == LONGITUD_CODIGO

    def test_longitud_custom(self) -> None:
        c = generar_codigo_verificacion(longitud=10)
        assert len(c) == 10

    def test_longitud_invalida_lanza(self) -> None:
        with pytest.raises(ValueError):
            generar_codigo_verificacion(longitud=0)
        with pytest.raises(ValueError):
            generar_codigo_verificacion(longitud=-1)

    def test_alfabeto_seguro_no_tiene_caracteres_ambiguos(self) -> None:
        for amb in ('0', 'O', '1', 'I', 'l'):
            assert amb not in _ALFABETO_SEGURO, f'caracter ambiguo en alfabeto: {amb!r}'

    def test_codigo_solo_usa_alfabeto_seguro(self) -> None:
        # Generamos varios para reducir chance de pasar por suerte.
        for _ in range(50):
            c = generar_codigo_verificacion()
            for ch in c:
                assert ch in _ALFABETO_SEGURO

    def test_codigos_son_distintos(self) -> None:
        """Estadísticamente improbable colisión con 32^6 espacio."""
        codigos = {generar_codigo_verificacion() for _ in range(100)}
        assert len(codigos) == 100  # sin duplicados en 100 tries


class TestValidar:
    def test_codigo_valido(self) -> None:
        assert es_codigo_valido('R2X9F4') is True

    def test_codigo_con_caracter_ambiguo(self) -> None:
        assert es_codigo_valido('R2O9F4') is False  # tiene O
        assert es_codigo_valido('R2I9F4') is False  # tiene I

    def test_vacio(self) -> None:
        assert es_codigo_valido('') is False
        assert es_codigo_valido(None) is False  # type: ignore[arg-type]

    def test_demasiado_largo(self) -> None:
        # Defensivo: limite 20 chars.
        assert es_codigo_valido('A' * 21) is False

    def test_caracteres_no_ascii(self) -> None:
        assert es_codigo_valido('ABCñDE') is False
