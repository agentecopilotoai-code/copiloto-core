"""Schemas Pydantic para GD-API-0041 — Alertas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoAlerta = Literal[
    'proximo_vencimiento', 'vencido', 'sin_asignar',
    'riesgo', 'seguridad', 'fallo_periferico', 'auto_proteccion',
]

SeveridadAlerta = Literal['informativa', 'media', 'alta', 'critica']

EstadoAlerta = Literal['activa', 'leida', 'gestionada', 'escalada', 'cerrada']


class AlertaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    destinatario_user_id: UUID | None = None
    destinatario_dependencia_id: UUID | None = None
    tipo_alerta: TipoAlerta
    severidad: SeveridadAlerta
    titulo: str
    mensaje: str
    entidad_relacionada_tipo: str | None = None
    entidad_relacionada_id: UUID | None = None
    estado: EstadoAlerta
    created_at: datetime


class AlertasListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[AlertaResponse]
    total_activas: int
    total_criticas: int


class AlertaEscalarRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    user_destino_id: UUID
    motivo: str = Field(min_length=10, max_length=500)


class AlertaMarcarGestionadaRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    observacion: str | None = Field(default=None, max_length=2000)


__all__ = [
    'TipoAlerta', 'SeveridadAlerta', 'EstadoAlerta',
    'AlertaResponse', 'AlertasListResponse',
    'AlertaEscalarRequest', 'AlertaMarcarGestionadaRequest',
]
