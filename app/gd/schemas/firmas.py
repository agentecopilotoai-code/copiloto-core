"""Schemas Pydantic para EP-011 firmas (bloque 12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoFirma = Literal['escaneada', 'electronica', 'digital']
EstadoFirmaDoc = Literal['pendiente', 'consumada', 'rechazada', 'revocada']
EstadoFirmaEscaneada = Literal['pendiente_autorizacion', 'activa', 'revocada']


# =============================================================================
# Firma escaneada (GD-API-0068)
# =============================================================================

class RegistrarFirmaEscaneadaRequest(BaseModel):
    """POST /api/v1/gd/firmas/escaneadas."""
    archivo_digital_id: UUID
    mime_type: str = Field(default='image/png', max_length=255)
    tamano_bytes: int | None = Field(default=None, ge=0)
    hash_sha256: str | None = Field(default=None, max_length=128)


class AutorizarFirmaEscaneadaRequest(BaseModel):
    """POST /api/v1/gd/firmas/escaneadas/{id}/autorizar."""
    pass  # solo requiere actor con permiso


class RevocarFirmaEscaneadaRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=2000)


class FirmaEscaneadaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    user_id: UUID
    archivo_digital_id: UUID
    mime_type: str
    tamano_bytes: int | None = None
    hash_sha256: str | None = None
    estado: EstadoFirmaEscaneada
    autorizada_por_user_id: UUID | None = None
    fecha_autorizacion: datetime | None = None
    motivo_revocacion: str | None = None
    created_at: datetime


class FirmaEscaneadaListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[FirmaEscaneadaResponse]
    total: int


# =============================================================================
# Firma electrónica de documento (GD-API-0069)
# =============================================================================

class FirmarElectronicaRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/firmar-electronica."""
    version_documento_id: UUID  # versión específica a firmar
    sesion_iniciada_en: datetime | None = None  # para validar step-up (>5min)
    step_up_satisfecho: bool = False  # True si re-auth ya realizada en cliente
    observaciones: str | None = Field(default=None, max_length=1000)


# =============================================================================
# Firma digital certificada (GD-API-0070)
# =============================================================================

class FirmarDigitalRequest(BaseModel):
    """POST /api/v1/gd/documentos/{id}/firmar-digital."""
    version_documento_id: UUID
    certificado_id: str = Field(min_length=2, max_length=255)
    proveedor: str = Field(min_length=2, max_length=64)
    # PIN no se envía aquí — el handler delega al provider via secure channel.
    # En tests se pasa como header opcional o se mockea el provider.


# =============================================================================
# Rechazo / revocación (GD-API-0071)
# =============================================================================

class RechazarFirmaRequest(BaseModel):
    observacion: str = Field(min_length=5, max_length=2000)


class RevocarFirmaConsumadaRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)


# =============================================================================
# Responses
# =============================================================================

class FirmaDocumentoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    documento_id: UUID
    version_documento_id: UUID
    firmante_user_id: UUID
    tipo_firma: TipoFirma
    estado: EstadoFirmaDoc
    firma_escaneada_id: UUID | None = None
    certificado_id: str | None = None
    proveedor_firma_digital: str | None = None
    hash_archivo: str
    hash_algoritmo: str
    snapshot_firmante: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None
    user_agent: str | None = None
    fecha_firma: datetime | None = None
    fecha_rechazo: datetime | None = None
    fecha_revocacion: datetime | None = None
    observaciones_rechazo: str | None = None
    motivo_revocacion: str | None = None
    step_up_requerido: bool
    created_at: datetime


class FirmaDocumentoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[FirmaDocumentoResponse]
    total: int


class EvidenciaFirmaResponse(BaseModel):
    """GET /api/v1/gd/firmas/{id}/evidencia (GD-API-0072)."""
    model_config = ConfigDict(frozen=True)
    firma: FirmaDocumentoResponse
    # Hash recalculable: si el caller pasa el archivo, podría re-verificar.
    hash_referencia: str
    hash_algoritmo: str
    # Información del documento + versión asociados.
    documento_titulo: str | None = None
    documento_version: int | None = None


__all__ = [
    # Enums
    'TipoFirma', 'EstadoFirmaDoc', 'EstadoFirmaEscaneada',
    # Requests
    'RegistrarFirmaEscaneadaRequest', 'AutorizarFirmaEscaneadaRequest',
    'RevocarFirmaEscaneadaRequest',
    'FirmarElectronicaRequest', 'FirmarDigitalRequest',
    'RechazarFirmaRequest', 'RevocarFirmaConsumadaRequest',
    # Responses
    'FirmaEscaneadaResponse', 'FirmaEscaneadaListResponse',
    'FirmaDocumentoResponse', 'FirmaDocumentoListResponse',
    'EvidenciaFirmaResponse',
]
