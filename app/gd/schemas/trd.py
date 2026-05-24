"""Schemas Pydantic para EP-015 TRD/TVD (bloque 16)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


EstadoVersionTRD = Literal['borrador', 'vigente', 'historica', 'archivada']
EstadoSerie = Literal['activa', 'inactiva']
EstadoSubserie = Literal['activa', 'inactiva']
EstadoTipoDocumental = Literal['activo', 'inactivo']
DisposicionFinal = Literal[
    'conservacion_total', 'seleccion', 'eliminacion', 'reproduccion',
]
EntidadClasificable = Literal[
    'radicado', 'documento', 'pqrsd', 'correspondencia', 'expediente',
]
EstadoClasificacion = Literal['vigente', 'reemplazada']


# =============================================================================
# Version TRD
# =============================================================================

class CrearVersionTRDRequest(BaseModel):
    codigo: str = Field(min_length=2, max_length=80, pattern=r'^[A-Z0-9\-_]+$')
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    fecha_aprobacion: date | None = None
    fecha_inicio_vigencia: date | None = None
    fecha_fin_vigencia: date | None = None

    @model_validator(mode='after')
    def _fechas(self):
        if (self.fecha_inicio_vigencia and self.fecha_fin_vigencia
                and self.fecha_fin_vigencia < self.fecha_inicio_vigencia):
            raise ValueError('fecha_fin_vigencia debe ser >= fecha_inicio_vigencia')
        return self


class ActivarVersionTRDRequest(BaseModel):
    """POST /trd/{id}/activar — marca como vigente y la anterior pasa a histórica."""
    pass


class VersionTRDResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    fecha_aprobacion: date | None = None
    fecha_inicio_vigencia: date | None = None
    fecha_fin_vigencia: date | None = None
    estado: EstadoVersionTRD
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class VersionTRDListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[VersionTRDResponse]
    total: int


# =============================================================================
# Series / subseries / tipos documentales
# =============================================================================

class CrearSerieRequest(BaseModel):
    version_trd_id: UUID
    codigo: str = Field(min_length=1, max_length=80)
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)


class SerieResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    version_trd_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    estado: EstadoSerie
    created_at: datetime


class CrearSubserieRequest(BaseModel):
    serie_id: UUID
    codigo: str = Field(min_length=1, max_length=80)
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    tiempo_archivo_gestion_anos: int | None = Field(default=None, ge=0, le=100)
    tiempo_archivo_central_anos: int | None = Field(default=None, ge=0, le=100)
    disposicion_final: DisposicionFinal | None = None


class SubserieResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    serie_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    tiempo_archivo_gestion_anos: int | None = None
    tiempo_archivo_central_anos: int | None = None
    disposicion_final: DisposicionFinal | None = None
    estado: EstadoSubserie
    created_at: datetime


class CrearTipoDocumentalRequest(BaseModel):
    subserie_id: UUID
    codigo: str = Field(min_length=1, max_length=80)
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)


class TipoDocumentalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    subserie_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    estado: EstadoTipoDocumental
    created_at: datetime


# =============================================================================
# Version TVD
# =============================================================================

class CrearVersionTVDRequest(BaseModel):
    codigo: str = Field(min_length=2, max_length=80, pattern=r'^[A-Z0-9\-_]+$')
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    version_trd_id: UUID | None = None
    fecha_aprobacion: date | None = None
    fecha_inicio_vigencia: date | None = None
    fecha_fin_vigencia: date | None = None


class VersionTVDResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    version_trd_id: UUID | None = None
    fecha_aprobacion: date | None = None
    fecha_inicio_vigencia: date | None = None
    fecha_fin_vigencia: date | None = None
    estado: EstadoVersionTRD  # mismos estados que TRD
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Asociación dependencia ↔ código documental (GD-API-0097)
# =============================================================================

class AsociarDepCodigoRequest(BaseModel):
    dependencia_id: UUID
    version_trd_id: UUID
    serie_id: UUID | None = None
    subserie_id: UUID | None = None

    @model_validator(mode='after')
    def _target(self):
        if not self.serie_id and not self.subserie_id:
            raise ValueError('Debe especificar serie_id o subserie_id')
        return self


class DepCodigoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    dependencia_id: UUID
    version_trd_id: UUID
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    creado_por_user_id: UUID
    created_at: datetime


# =============================================================================
# Clasificación documental (GD-API-0098/0099)
# =============================================================================

class ClasificarDocumentalRequest(BaseModel):
    entidad_tipo: EntidadClasificable
    entidad_id: UUID
    version_trd_id: UUID
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    tipo_documental_id: UUID | None = None
    justificacion: str | None = Field(default=None, max_length=2000)


class ClasificacionDocumentalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    entidad_tipo: EntidadClasificable
    entidad_id: UUID
    version_trd_id: UUID
    serie_id: UUID | None = None
    subserie_id: UUID | None = None
    tipo_documental_id: UUID | None = None
    justificacion: str | None = None
    estado: EstadoClasificacion
    clasificado_por_user_id: UUID
    fecha_clasificacion: datetime
    reemplazada_por_id: UUID | None = None
    created_at: datetime


class HistorialClasificacionResponse(BaseModel):
    """GD-API-0099 — historial de clasificaciones por entidad."""
    model_config = ConfigDict(frozen=True)
    entidad_tipo: EntidadClasificable
    entidad_id: UUID
    vigente: ClasificacionDocumentalResponse | None = None
    historial: list[ClasificacionDocumentalResponse]


__all__ = [
    # Enums
    'EstadoVersionTRD', 'EstadoSerie', 'EstadoSubserie',
    'EstadoTipoDocumental', 'DisposicionFinal',
    'EntidadClasificable', 'EstadoClasificacion',
    # Requests
    'CrearVersionTRDRequest', 'ActivarVersionTRDRequest',
    'CrearSerieRequest', 'CrearSubserieRequest', 'CrearTipoDocumentalRequest',
    'CrearVersionTVDRequest',
    'AsociarDepCodigoRequest',
    'ClasificarDocumentalRequest',
    # Responses
    'VersionTRDResponse', 'VersionTRDListResponse',
    'SerieResponse', 'SubserieResponse', 'TipoDocumentalResponse',
    'VersionTVDResponse',
    'DepCodigoResponse',
    'ClasificacionDocumentalResponse', 'HistorialClasificacionResponse',
]
