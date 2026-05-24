"""Schemas Pydantic para GD-API-0007 — Política de contraseñas.

Contratos en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 5.
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PoliticaContrasenaResponse(BaseModel):
    """Response GET /api/v1/gd/seguridad/politica."""
    model_config = ConfigDict(frozen=True)

    longitud_minima: int
    complejidad_regex: str
    historial_no_reuso: int
    vigencia_dias: int
    intentos_fallidos_max: int
    cooldown_segundos: int
    vigente_desde: datetime
    es_global: bool = Field(
        description='True si esta política es la global default (tenant_id IS NULL); '
                    'False si es específica del tenant.'
    )


class PoliticaContrasenaPatch(BaseModel):
    """PATCH /api/v1/gd/seguridad/politica body. Cualquier subset de campos."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    longitud_minima: int | None = Field(default=None, ge=6, le=256)
    complejidad_regex: str | None = Field(default=None, min_length=1, max_length=1000)
    historial_no_reuso: int | None = Field(default=None, ge=0, le=100)
    vigencia_dias: int | None = Field(default=None, ge=1, le=3650)
    intentos_fallidos_max: int | None = Field(default=None, ge=1, le=100)
    cooldown_segundos: int | None = Field(default=None, ge=0, le=86400)

    @field_validator('complejidad_regex')
    @classmethod
    def _regex_valida(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f'complejidad_regex no es una regex válida: {e}') from e
        return v


__all__ = [
    'PoliticaContrasenaResponse',
    'PoliticaContrasenaPatch',
]
