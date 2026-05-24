"""Schemas Pydantic para GD-API-0023 — Consecutivos transaccionales de radicación.

NOTA: este es schema interno; el endpoint público de radicación (GD-API-0024)
no expone la generación de consecutivos directamente — la usa internamente
cuando se crea un radicado de entrada/salida.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoRadicado = Literal['entrada', 'salida', 'interno', 'otro']

EstadoConsecutivo = Literal['activo', 'cerrado']


class ConsecutivoResponse(BaseModel):
    """Una fila de gd.consecutivo_radicacion."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    vigencia: int
    tipo_radicado: TipoRadicado
    prefijo: str
    ultimo_numero: int
    formato: str
    estado: EstadoConsecutivo


class ConsecutivosListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ConsecutivoResponse]


class SiguienteRadicadoRequest(BaseModel):
    """Body para POST /api/v1/gd/consecutivos/siguiente (uso interno + debugging)."""
    model_config = ConfigDict(frozen=True)

    vigencia: int = Field(ge=2020, le=2100)
    tipo_radicado: TipoRadicado


class SiguienteRadicadoResponse(BaseModel):
    """Response con el número generado."""
    model_config = ConfigDict(frozen=True)

    numero_radicado: str
    vigencia: int
    tipo_radicado: TipoRadicado


__all__ = [
    'TipoRadicado',
    'EstadoConsecutivo',
    'ConsecutivoResponse',
    'ConsecutivosListResponse',
    'SiguienteRadicadoRequest',
    'SiguienteRadicadoResponse',
]
