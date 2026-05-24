"""Schemas Pydantic para EP-019/020 utilidades (bloque 20).

Agrupa: auditoría consulta, catálogo eventos, constancia pública,
tipos doc identidad, versionado jerárquico dependencias, contingencia,
hoja control + índice electrónico.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Auditoría consulta (GD-API-0119)
# =============================================================================

class EventoAuditoriaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_evento: str
    dominio: str
    accion: str
    actor_type: str
    actor_id: UUID | None = None
    entidad_tipo: str | None = None
    entidad_id: UUID | None = None
    criticidad: str
    request_id: UUID | None = None
    ip: str | None = None
    valor_anterior: dict[str, Any] | None = None
    valor_nuevo: dict[str, Any] | None = None
    justificacion: str | None = None
    detalles: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventoAuditoriaListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[EventoAuditoriaResponse]
    total: int
    next_cursor: str | None = None


# =============================================================================
# Catálogo eventos (GD-API-0120)
# =============================================================================

class EventoCatalogoItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_evento: str
    dominio: str
    productor_modulo: str | None = None
    criticidad_default: str
    rnf_cubierto: list[str] = Field(default_factory=list)
    permiso_lectura: str | None = None
    descripcion: str | None = None
    activo: bool


class EventoCatalogoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[EventoCatalogoItem]
    total: int


# =============================================================================
# Constancia pública (GD-API-0122)
# =============================================================================

class ConstanciaPublicaResponse(BaseModel):
    """Respuesta pública (sin auth) de GET /gd/verificar/{codigo}.
    NO expone datos personales del tercero ni cuerpo del trámite.
    """
    model_config = ConfigDict(frozen=True)
    numero_radicado: str
    fecha_radicacion: datetime
    tipo_radicado: str
    estado_actual: str
    dependencia_actual_publica: str | None = None
    asunto_resumido: str
    valida: bool = True


# =============================================================================
# Tipos documento identidad (GD-API-0123)
# =============================================================================

class TipoDocIdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    codigo: str
    nombre: str
    pais_iso: str
    formato_regex: str | None = None
    activo_global: bool


class OrgTipoDocResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo_tipo_doc: str
    activado: bool
    es_default: bool
    created_at: datetime


class PatchOrgTipoDocRequest(BaseModel):
    """PATCH /organizacion/tipos-documento — actualiza selección + default."""
    codigos_activos: list[str] = Field(min_length=1, max_length=50)
    codigo_default: str | None = None


# =============================================================================
# Cambios dependencia (GD-API-0124)
# =============================================================================

class RelacionDepHistResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    dependencia_id: UUID
    dependencia_padre_id: UUID | None = None
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date | None = None
    tipo_cambio: str
    motivo_cambio: str | None = None
    acto_administrativo: str | None = None
    registrado_por_user_id: UUID
    created_at: datetime


class HistorialDepResponse(BaseModel):
    """GET /estructura/dependencias/{id}/historial."""
    model_config = ConfigDict(frozen=True)
    dependencia_id: UUID
    relaciones: list[RelacionDepHistResponse]


class FusionarRequest(BaseModel):
    """POST /estructura/fusionar."""
    dependencias_origen: list[UUID] = Field(min_length=1, max_length=10)
    dependencia_destino_id: UUID
    fecha_vigencia: date
    motivo: str = Field(min_length=10, max_length=2000)
    acto_administrativo: str | None = Field(default=None, max_length=500)


class FusionarResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    dependencia_destino_id: UUID
    relaciones_creadas: list[UUID]
    dependencias_cerradas: list[UUID]


# =============================================================================
# Radicación contingencia (GD-API-0125)
# =============================================================================

class RadicarContingenciaRequest(BaseModel):
    """POST /ventanilla/radicados/contingencia."""
    numero_radicado_manual: str = Field(min_length=2, max_length=80)
    fecha_radicacion_real: datetime
    justificacion: str = Field(min_length=20, max_length=2000)
    evidencia_contingencia_archivo_id: UUID
    # Resto de campos normales de un radicado:
    canal_id: UUID
    tipo_radicado: Literal['entrada', 'salida', 'interno'] = 'entrada'
    asunto: str = Field(min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    tercero_id: UUID | None = None
    dependencia_destino_id: UUID | None = None


class RadicarContingenciaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    radicado_id: UUID
    numero_radicado: str
    fecha_radicacion_real: datetime
    fecha_ingreso_sistema: datetime
    es_contingencia: bool = True


# =============================================================================
# Hoja de control + índice electrónico expediente (GD-API-0126)
# =============================================================================

class HojaControlEntradaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    expediente_id: UUID
    fecha: datetime
    evento: str
    descripcion: str | None = None
    usuario_id: UUID
    snapshot_jsonb: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class HojaControlListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    expediente_id: UUID
    items: list[HojaControlEntradaResponse]
    total: int


class GenerarIndiceRequest(BaseModel):
    """POST /expedientes/{id}/indice-electronico."""
    pass


class IndiceElectronicoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    expediente_id: UUID
    version_indice: int
    generado_en: datetime
    generado_por_user_id: UUID
    contenido_jsonb: dict[str, Any] = Field(default_factory=dict)
    hash_sha256: str | None = None


__all__ = [
    # Auditoría
    'EventoAuditoriaResponse', 'EventoAuditoriaListResponse',
    'EventoCatalogoItem', 'EventoCatalogoListResponse',
    # Constancia pública
    'ConstanciaPublicaResponse',
    # Tipos doc identidad
    'TipoDocIdResponse', 'OrgTipoDocResponse', 'PatchOrgTipoDocRequest',
    # Cambios dependencia
    'RelacionDepHistResponse', 'HistorialDepResponse',
    'FusionarRequest', 'FusionarResponse',
    # Contingencia
    'RadicarContingenciaRequest', 'RadicarContingenciaResponse',
    # Hoja control + índice
    'HojaControlEntradaResponse', 'HojaControlListResponse',
    'GenerarIndiceRequest', 'IndiceElectronicoResponse',
]
