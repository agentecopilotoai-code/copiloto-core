"""Schemas Pydantic para GD-API-0015 — Parámetros institucionales versionados."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoParametro = Literal['string', 'integer', 'boolean', 'json', 'decimal']

EstadoParametro = Literal['activo', 'reemplazado']


class ParametroResponse(BaseModel):
    """Un parámetro vigente o histórico."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    clave: str
    valor: str  # raw, sin parsear según tipo (la UI/llamador hace el parse)
    tipo: TipoParametro
    descripcion: str | None = None
    vigente_desde: datetime
    vigente_hasta: datetime | None = None
    estado: EstadoParametro


class ParametroDetalleResponse(BaseModel):
    """Response GET /api/v1/gd/parametros/{clave} — incluye historial."""
    model_config = ConfigDict(frozen=True)

    clave: str
    vigente: ParametroResponse | None = None
    historial: list[ParametroResponse] = Field(default_factory=list)


class ParametrosListResponse(BaseModel):
    """Response GET /api/v1/gd/parametros — solo vigentes."""
    model_config = ConfigDict(frozen=True)

    items: list[ParametroResponse]


class ParametroUpsert(BaseModel):
    """Un parámetro dentro del PATCH masivo."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    clave: str = Field(min_length=2, max_length=200)
    valor: str = Field(min_length=0, max_length=10_000)
    tipo: TipoParametro = 'string'
    descripcion: str | None = Field(default=None, max_length=2000)
    motivo: str = Field(min_length=5, max_length=500)


class ParametrosPatch(BaseModel):
    """PATCH /api/v1/gd/parametros body."""
    model_config = ConfigDict(frozen=True, extra='forbid')

    parametros: list[ParametroUpsert] = Field(min_length=1, max_length=100)


__all__ = [
    'TipoParametro',
    'EstadoParametro',
    'ParametroResponse',
    'ParametroDetalleResponse',
    'ParametrosListResponse',
    'ParametroUpsert',
    'ParametrosPatch',
]
