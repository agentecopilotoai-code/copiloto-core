"""Schemas Pydantic para EP-017 RPA + APIs públicas (bloque 18)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoIdentidad = Literal['agente_ia', 'robot_rpa', 'integrador']
EstadoIdentidad = Literal['activa', 'revocada', 'suspendida']
EstadoTareaRPA = Literal[
    'pending', 'in_progress', 'done', 'failed', 'cancelled',
]
PrioridadTarea = Literal['baja', 'normal', 'alta', 'urgente']
EstadoWebhookSub = Literal['activa', 'inactiva', 'pausada']
EstadoWebhookDelivery = Literal[
    'pending', 'in_progress', 'delivered', 'failed', 'expirado',
]


# =============================================================================
# Identidad técnica (GD-API-0105)
# =============================================================================

class CrearIdentidadTecnicaRequest(BaseModel):
    codigo: str = Field(min_length=2, max_length=80, pattern=r'^[A-Z0-9_]+$')
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    tipo: TipoIdentidad
    scopes: list[str] = Field(default_factory=list)
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=100000)
    dependencia_alcance_id: UUID | None = None


class RevocarIdentidadRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)


class RotarApiKeyRequest(BaseModel):
    """POST /identidades-tecnicas/{id}/rotar-key — devuelve nuevo key una vez."""
    pass


class IdentidadTecnicaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    tipo: TipoIdentidad
    api_key_prefijo: str | None = None
    scopes: list[str] = Field(default_factory=list)
    estado: EstadoIdentidad
    rate_limit_rpm: int | None = None
    ultimo_uso_en: datetime | None = None
    total_requests: int
    dependencia_alcance_id: UUID | None = None
    motivo_revocacion: str | None = None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class IdentidadTecnicaCreadaResponse(IdentidadTecnicaResponse):
    """Solo en respuesta a CREATE / rotar-key: devuelve la API key una vez."""
    api_key: str  # ¡Solo aparece en el response del create/rotar!


class IdentidadListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[IdentidadTecnicaResponse]
    total: int


# =============================================================================
# Tareas RPA (GD-API-0106)
# =============================================================================

class CrearTareaRPARequest(BaseModel):
    tipo: str = Field(min_length=2, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    prioridad: PrioridadTarea = 'normal'
    identidad_tecnica_id: UUID | None = None  # NULL = bandeja general


class ReclamarTareaRequest(BaseModel):
    """POST /rpa/tareas/reclamar — atomically claim next pending task.
    identidad_tecnica_id se infiere del API key del request.
    """
    tipo: str | None = Field(default=None, max_length=100)
    ttl_segundos: int = Field(default=300, ge=30, le=3600)


class ReportarResultadoRequest(BaseModel):
    """POST /rpa/tareas/{id}/resultado."""
    claim_token: UUID
    estado: Literal['done', 'failed']
    resultado: dict[str, Any] | None = None
    error_texto: str | None = Field(default=None, max_length=4000)
    error_codigo: str | None = Field(default=None, max_length=80)


class TareaRPAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    identidad_tecnica_id: UUID | None = None
    tipo: str
    payload: dict[str, Any] = Field(default_factory=dict)
    prioridad: PrioridadTarea
    estado: EstadoTareaRPA
    resultado: dict[str, Any] | None = None
    error_texto: str | None = None
    error_codigo: str | None = None
    claim_token: UUID | None = None
    claim_expira_en: datetime | None = None
    created_by_user_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class TareaRPAListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[TareaRPAResponse]
    total: int


# =============================================================================
# Webhooks (GD-API-0108)
# =============================================================================

class CrearWebhookSubRequest(BaseModel):
    identidad_tecnica_id: UUID
    url: str = Field(min_length=10, max_length=1024,
                      pattern=r'^https?://')
    eventos_suscritos: list[str] = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    max_intentos: int = Field(default=5, ge=1, le=20)
    backoff_inicial_segundos: int = Field(default=30, ge=1, le=3600)
    backoff_max_segundos: int = Field(default=3600, ge=60, le=86400)


class PatchWebhookSubRequest(BaseModel):
    url: str | None = Field(default=None, min_length=10, max_length=1024,
                              pattern=r'^https?://')
    eventos_suscritos: list[str] | None = None
    descripcion: str | None = None
    estado: EstadoWebhookSub | None = None
    max_intentos: int | None = Field(default=None, ge=1, le=20)
    backoff_inicial_segundos: int | None = Field(default=None, ge=1, le=3600)
    backoff_max_segundos: int | None = Field(default=None, ge=60, le=86400)


class WebhookSubResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    identidad_tecnica_id: UUID
    url: str
    eventos_suscritos: list[str]
    descripcion: str | None = None
    estado: EstadoWebhookSub
    max_intentos: int
    backoff_inicial_segundos: int
    backoff_max_segundos: int
    total_eventos_entregados: int
    total_eventos_fallidos: int
    ultimo_evento_en: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookSubCreadaResponse(WebhookSubResponse):
    """Solo en CREATE: devuelve el secret una vez."""
    secret: str


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    suscripcion_id: UUID
    evento_id: UUID
    tipo_evento: str
    estado: EstadoWebhookDelivery
    intentos: int
    http_status: int | None = None
    ultimo_intento_en: datetime | None = None
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None
    error_texto: str | None = None
    created_at: datetime


class WebhookDeliveryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[WebhookDeliveryResponse]
    total: int


# =============================================================================
# Rate limit (GD-API-0109)
# =============================================================================

class RateLimitInfo(BaseModel):
    """Información de rate limit para una identidad técnica."""
    model_config = ConfigDict(frozen=True)
    identidad_tecnica_id: UUID
    rate_limit_rpm: int | None = None
    ventana_actual: datetime
    contador_actual: int
    permitido: bool
    retry_after_segundos: int | None = None


__all__ = [
    # Enums
    'TipoIdentidad', 'EstadoIdentidad', 'EstadoTareaRPA',
    'PrioridadTarea', 'EstadoWebhookSub', 'EstadoWebhookDelivery',
    # Identidad técnica
    'CrearIdentidadTecnicaRequest', 'RevocarIdentidadRequest',
    'RotarApiKeyRequest', 'IdentidadTecnicaResponse',
    'IdentidadTecnicaCreadaResponse', 'IdentidadListResponse',
    # Tareas RPA
    'CrearTareaRPARequest', 'ReclamarTareaRequest',
    'ReportarResultadoRequest', 'TareaRPAResponse', 'TareaRPAListResponse',
    # Webhooks
    'CrearWebhookSubRequest', 'PatchWebhookSubRequest',
    'WebhookSubResponse', 'WebhookSubCreadaResponse',
    'WebhookDeliveryResponse', 'WebhookDeliveryListResponse',
    # Rate limit
    'RateLimitInfo',
]
