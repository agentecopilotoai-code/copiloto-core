"""Generador de códigos de verificación para constancias públicas de radicado.

Reglas:
- 6 caracteres ASCII uppercase.
- Excluir caracteres ambiguos: 0/O, 1/I/l (la 'l' minúscula no aplica porque
  todo es uppercase, pero 'I' y 'O' sí).
- Alfabeto efectivo: 32 chars → 32^6 = ~1.07B combinaciones.
- Generar con `secrets` (crypto-safe, no `random`).

Uso: el handler GD-API-0024 llama `generar_codigo_verificacion()`. Si por azar
colisiona (probabilidad ~1 en 1B), el caller reintenta hasta 5 veces.
"""
from __future__ import annotations

import secrets


# 32 caracteres: A-Z sin I, O. 0-9 sin 0, 1.
# 24 letras (sin I, O) + 8 dígitos (2-9) = 32.
_ALFABETO_SEGURO = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

LONGITUD_CODIGO = 6


def generar_codigo_verificacion(longitud: int = LONGITUD_CODIGO) -> str:
    """Genera un código alfanumérico aleatorio sin caracteres ambiguos.

    Args:
        longitud: longitud del código (default 6).

    Returns:
        str del código, ej. "R2X9F4" o "ABCD23".

    Raises:
        ValueError: si longitud < 1.
    """
    if longitud < 1:
        raise ValueError(f'longitud debe ser >= 1, recibido {longitud}')
    return ''.join(secrets.choice(_ALFABETO_SEGURO) for _ in range(longitud))


def es_codigo_valido(codigo: str) -> bool:
    """Valida que un código solo contiene caracteres del alfabeto seguro.

    Útil para sanitizar inputs públicos en `GET /gd/verificar/{codigo}`.
    """
    if not codigo or len(codigo) > 20:  # límite defensivo
        return False
    return all(c in _ALFABETO_SEGURO for c in codigo)


__all__ = [
    'LONGITUD_CODIGO',
    'generar_codigo_verificacion',
    'es_codigo_valido',
]
