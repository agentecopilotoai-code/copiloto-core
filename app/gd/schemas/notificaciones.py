"""Schemas Pydantic para GD-API-0040 — Notificaciones."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


CanalNotificacion = Literal['in_app', 'correo', 'webhook']


class NotificacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    destinatario_user_id: UUID
    tipo_notificacion: str
    titulo: str
    mensaje: str
    entidad_origen_tipo: str | None = None
    entidad_origen_id: UUID | None = None
    enviada_por_canal: list[CanalNotificacion]
    leida: bool
    fecha_lectura: datetime | None = None
    created_at: datetime


class NotificacionesListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[NotificacionResponse]
    no_leidas: int
    total: int


class NotificacionMarcarLeidaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    leida: bool
    fecha_lectura: datetime


class NotificacionPreferenciaItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    tipo_notificacion: str
    in_app_habilitado: bool
    correo_habilitado: bool


class NotificacionPreferenciasResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    preferencias: list[NotificacionPreferenciaItem]


class NotificacionPreferenciaUpsert(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    tipo_notificacion: str = Field(min_length=3, max_length=100)
    in_app_habilitado: bool = True
    correo_habilitado: bool = True


class NotificacionPreferenciasPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    preferencias: list[NotificacionPreferenciaUpsert] = Field(min_length=1, max_length=50)


__all__ = [
    'CanalNotificacion',
    'NotificacionResponse', 'NotificacionesListResponse',
    'NotificacionMarcarLeidaResponse',
    'NotificacionPreferenciaItem', 'NotificacionPreferenciasResponse',
    'NotificacionPreferenciaUpsert', 'NotificacionPreferenciasPatch',
]
