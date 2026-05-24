"""Schemas Pydantic para EP-016 expediente electrónico (bloque 17)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EstadoExpediente = Literal[
    'abierto', 'cerrado', 'reabierto', 'transferido', 'anulado',
]
ItemTipo = Literal['documento', 'radicado', 'pqrsd', 'correspondencia']
EstadoItem = Literal['vinculado', 'retirado']


# =============================================================================
# Requests
# =============================================================================

class CrearExpedienteRequest(BaseModel):
    codigo: str = Field(min_length=2, max_length=80)
    titulo: str = Field(min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    dependencia_responsable_id: UUID | None = None
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchExpedienteRequest(BaseModel):
    titulo: str | None = Field(default=None, min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    dependencia_responsable_id: UUID | None = None
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class CerrarExpedienteRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=2000)


class ReabrirExpedienteRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)


class TransferirExpedienteRequest(BaseModel):
    destino: str = Field(min_length=2, max_length=255)
    motivo: str = Field(min_length=10, max_length=2000)


class AsociarItemRequest(BaseModel):
    """POST /expedientes/{id}/items (genérico) o helpers /documentos /radicados."""
    item_tipo: ItemTipo
    item_id: UUID
    orden: int = Field(default=0, ge=0)


class RetirarItemRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)


# =============================================================================
# Responses
# =============================================================================

class ExpedienteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    titulo: str
    descripcion: str | None = None
    dependencia_responsable_id: UUID | None = None
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    estado: EstadoExpediente
    fecha_apertura: datetime
    fecha_cierre: datetime | None = None
    fecha_reapertura: datetime | None = None
    fecha_transferencia: datetime | None = None
    motivo_cierre: str | None = None
    motivo_reapertura: str | None = None
    motivo_transferencia: str | None = None
    destino_transferencia: str | None = None
    abierto_por_user_id: UUID
    cerrado_por_user_id: UUID | None = None
    reabierto_por_user_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ExpedienteListItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    titulo: str
    estado: EstadoExpediente
    dependencia_responsable_id: UUID | None = None
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    fecha_apertura: datetime
    fecha_cierre: datetime | None = None
    abierto_por_user_id: UUID


class ExpedienteListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[ExpedienteListItem]
    total: int


class ExpedienteItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    expediente_id: UUID
    item_tipo: ItemTipo
    item_id: UUID
    orden: int
    estado: EstadoItem
    vinculado_por_user_id: UUID
    fecha_vinculacion: datetime
    retirado_por_user_id: UUID | None = None
    fecha_retiro: datetime | None = None
    motivo_retiro: str | None = None


class ContenidoExpedienteResponse(BaseModel):
    """GD-API-0103: contenido agregado del expediente."""
    model_config = ConfigDict(frozen=True)
    expediente: ExpedienteResponse
    items_vinculados: list[ExpedienteItemResponse]
    items_retirados: list[ExpedienteItemResponse]
    totales_por_tipo: dict[str, int]


__all__ = [
    # Enums
    'EstadoExpediente', 'ItemTipo', 'EstadoItem',
    # Requests
    'CrearExpedienteRequest', 'PatchExpedienteRequest',
    'CerrarExpedienteRequest', 'ReabrirExpedienteRequest',
    'TransferirExpedienteRequest',
    'AsociarItemRequest', 'RetirarItemRequest',
    # Responses
    'ExpedienteResponse', 'ExpedienteListItem', 'ExpedienteListResponse',
    'ExpedienteItemResponse', 'ContenidoExpedienteResponse',
]
