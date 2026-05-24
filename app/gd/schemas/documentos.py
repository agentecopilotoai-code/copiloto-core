"""Schemas Pydantic para EP-009 documentos, anexos y versiones (bloque 10)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ClasificacionInformacion = Literal[
    'publica', 'interna', 'reservada', 'confidencial',
    'datos_personales', 'sensible',
]

EstadoDocumento = Literal['activo', 'anulado', 'reemplazado', 'archivado']
EstadoVersion = Literal[
    'borrador', 'aprobada', 'firmada', 'publicada', 'reemplazada', 'anulada',
]

EntidadRelacionadaTipo = Literal[
    'radicado', 'pqrsd', 'correspondencia', 'documento',
]
EntidadDocumentoTipo = Literal[
    'radicado', 'pqrsd', 'correspondencia', 'expediente',
]


# =============================================================================
# Documento — CRUD (GD-API-0057, 0059, 0063)
# =============================================================================

class CrearDocumentoRequest(BaseModel):
    """POST /api/v1/gd/documentos.

    Crea documento + primera versión apuntando a un archivo_digital_id existente
    (entregado por EP-018 / GD-API-0110). Mientras EP-018 no aterrice, el caller
    pasa un UUID arbitrario.
    """
    titulo: str = Field(min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    clasificacion_informacion: ClasificacionInformacion = 'interna'
    trd_serie_codigo: str | None = Field(default=None, max_length=50)
    trd_subserie_codigo: str | None = Field(default=None, max_length=50)
    trd_tipo_documental: str | None = Field(default=None, max_length=255)
    # Primera versión:
    archivo_digital_id: UUID
    mime_type: str | None = Field(default=None, max_length=255)
    tamano_bytes: int | None = Field(default=None, ge=0)
    hash_sha256: str | None = Field(default=None, max_length=128)
    observaciones: str | None = Field(default=None, max_length=2000)


class NuevaVersionRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/versiones."""
    archivo_digital_id: UUID
    mime_type: str | None = Field(default=None, max_length=255)
    tamano_bytes: int | None = Field(default=None, ge=0)
    hash_sha256: str | None = Field(default=None, max_length=128)
    observaciones: str | None = Field(default=None, max_length=2000)


class AnularDocumentoRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/anular."""
    motivo: str = Field(min_length=10, max_length=2000)


class ReemplazarDocumentoRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/reemplazar.

    Crea una NUEVA versión y marca la versión anterior como 'reemplazada'.
    """
    archivo_digital_id: UUID
    motivo: str = Field(min_length=5, max_length=2000)
    mime_type: str | None = Field(default=None, max_length=255)
    tamano_bytes: int | None = Field(default=None, ge=0)
    hash_sha256: str | None = Field(default=None, max_length=128)


# =============================================================================
# Anexos (GD-API-0060)
# =============================================================================

class CrearAnexoRequest(BaseModel):
    """POST /api/v1/gd/anexos."""
    archivo_digital_id: UUID
    entidad_relacionada_tipo: EntidadRelacionadaTipo
    entidad_relacionada_id: UUID
    titulo: str | None = Field(default=None, min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    mime_type: str | None = Field(default=None, max_length=255)
    tamano_bytes: int | None = Field(default=None, ge=0)


# =============================================================================
# Relaciones documento ↔ entidad (GD-API-0057, derivado)
# =============================================================================

class RelacionarDocumentoRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/relacionar."""
    entidad_tipo: EntidadDocumentoTipo
    entidad_id: UUID
    rol: str | None = Field(default='principal', max_length=50)


# =============================================================================
# Response models
# =============================================================================

class VersionDocumentoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    documento_id: UUID
    numero_version: int
    archivo_digital_id: UUID
    mime_type: str | None = None
    tamano_bytes: int | None = None
    hash_sha256: str | None = None
    estado: EstadoVersion
    creado_por_user_id: UUID
    aprobado_por_user_id: UUID | None = None
    firmado_por_user_id: UUID | None = None
    observaciones: str | None = None
    created_at: datetime


class DocumentoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    titulo: str
    descripcion: str | None = None
    clasificacion_informacion: ClasificacionInformacion
    trd_serie_codigo: str | None = None
    trd_subserie_codigo: str | None = None
    trd_tipo_documental: str | None = None
    estado: EstadoDocumento
    version_vigente_id: UUID | None = None
    numero_version_vigente: int
    anulado_en: datetime | None = None
    motivo_anulacion: str | None = None
    reemplazado_por_documento_id: UUID | None = None
    creado_por_user_id: UUID
    created_at: datetime
    updated_at: datetime
    versiones: list[VersionDocumentoResponse] = Field(default_factory=list)


class DocumentoListItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    titulo: str
    clasificacion_informacion: ClasificacionInformacion
    estado: EstadoDocumento
    numero_version_vigente: int
    trd_serie_codigo: str | None = None
    creado_por_user_id: UUID
    created_at: datetime


class DocumentoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[DocumentoListItem]
    total: int


class AnexoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    archivo_digital_id: UUID
    entidad_relacionada_tipo: EntidadRelacionadaTipo
    entidad_relacionada_id: UUID
    titulo: str | None = None
    descripcion: str | None = None
    mime_type: str | None = None
    tamano_bytes: int | None = None
    creado_por_user_id: UUID
    created_at: datetime


class AnexoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[AnexoResponse]
    total: int


class DescargaResponse(BaseModel):
    """Respuesta GET /archivos/{id}/descargar.

    NOTA: el binario real lo entrega EP-018. Aquí devolvemos URL pre-firmada
    o token + log de auditoría. Mientras tanto, devolvemos solo el log_id +
    información necesaria.
    """
    model_config = ConfigDict(frozen=True)
    archivo_digital_id: UUID
    descarga_id: UUID
    clasificacion_informacion: ClasificacionInformacion
    descargado_en: datetime
    # URL pre-firmada o token que el caller usa para hacer el GET binario
    # (servido por EP-018). Placeholder mientras EP-018 no exista.
    download_url: str | None = None


class RelacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    documento_id: UUID
    entidad_tipo: EntidadDocumentoTipo
    entidad_id: UUID
    rol: str | None = None
    creado_por_user_id: UUID
    created_at: datetime


__all__ = [
    # Enums
    'ClasificacionInformacion', 'EstadoDocumento', 'EstadoVersion',
    'EntidadRelacionadaTipo', 'EntidadDocumentoTipo',
    # Requests
    'CrearDocumentoRequest', 'NuevaVersionRequest',
    'AnularDocumentoRequest', 'ReemplazarDocumentoRequest',
    'CrearAnexoRequest', 'RelacionarDocumentoRequest',
    # Responses
    'VersionDocumentoResponse', 'DocumentoResponse',
    'DocumentoListItem', 'DocumentoListResponse',
    'AnexoResponse', 'AnexoListResponse',
    'DescargaResponse', 'RelacionResponse',
]
