"""Schemas Pydantic para EP-018 servicio transversal archivos (bloque 19)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


StorageBackend = Literal['filesystem', 's3', 'azure_blob', 'memory']
EstadoArchivo = Literal[
    'cargado', 'extrayendo', 'listo', 'bloqueado', 'anulado', 'purgado',
]
AntivirusEstado = Literal['pendiente', 'limpio', 'infectado', 'error']
Proposito = Literal[
    'general', 'knowledge', 'gd.documento', 'gd.anexo',
    'gd.constancia', 'gd.firma_imagen', 'gd.acuse_recibido',
    'gd.plantilla_base',
]
RetencionPolitica = Literal[
    'estandar', 'conservacion_total', 'eliminacion',
    'seleccion', 'reproduccion',
]


# =============================================================================
# Subida (multipart se maneja en handler, este schema es para metadata extra)
# =============================================================================

class SubirArchivoMetadata(BaseModel):
    """Metadata adicional en el multipart upload (form fields)."""
    proposito: Proposito = 'general'
    contexto_entidad_tipo: str | None = Field(default=None, max_length=80)
    contexto_entidad_id: UUID | None = None
    retencion_politica: RetencionPolitica | None = None
    storage_backend: StorageBackend = 'filesystem'
    encriptado_at_rest: bool = False


class AttachPropositoRequest(BaseModel):
    """POST /core/archivos/{id}/attach-proposito."""
    proposito: Proposito
    contexto_entidad_tipo: str | None = Field(default=None, max_length=80)
    contexto_entidad_id: UUID | None = None


class ReextraerRequest(BaseModel):
    """POST /core/archivos/{id}/reextraer."""
    motor: Literal['pypdf', 'tesseract', 'openpyxl', 'auto'] = 'auto'


class AplicarRetencionRequest(BaseModel):
    """POST /core/archivos/aplicar-retencion (admin/cron)."""
    dry_run: bool = True
    limit: int = Field(default=100, ge=1, le=1000)


class AnularArchivoRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)


# =============================================================================
# Responses
# =============================================================================

class ArchivoDigitalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    nombre_original: str
    extension: str | None = None
    mime_type: str
    tamano_bytes: int
    hash_sha256: str
    hash_md5: str | None = None
    storage_backend: StorageBackend
    ruta_almacenamiento: str | None = None
    encriptado_at_rest: bool
    proposito: Proposito
    contexto_entidad_tipo: str | None = None
    contexto_entidad_id: UUID | None = None
    estado: EstadoArchivo
    analisis_antivirus: AntivirusEstado
    motor_antivirus: str | None = None
    fecha_antivirus: datetime | None = None
    detalle_antivirus: str | None = None
    retencion_politica: RetencionPolitica | None = None
    fecha_elegible_purga: datetime | None = None
    fecha_purga_bytes: datetime | None = None
    motivo_purga: str | None = None
    cargado_por_user_id: UUID
    cargado_en: datetime
    ultimo_acceso_en: datetime | None = None
    total_descargas: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchivoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[ArchivoDigitalResponse]
    total: int


class DescargaArchivoResponse(BaseModel):
    """Respuesta de POST /core/archivos/{id}/descargar."""
    model_config = ConfigDict(frozen=True)
    archivo_id: UUID
    descarga_id: UUID
    descargado_en: datetime
    # URL pre-firmada o token de descarga.
    download_url: str
    expira_en: datetime | None = None
    requiere_antivirus_check: bool = False


class ExtraccionResultadoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    archivo_digital_id: UUID
    motor: str
    version: str | None = None
    texto_completo: str | None = None
    paginas: list[dict[str, Any]] = Field(default_factory=list)
    confianza: float | None = None
    warning_baja_confianza: bool
    truncado: bool
    motivo_truncado: str | None = None
    extraido_en: datetime
    duracion_ms: int | None = None


class DuplicadosResponse(BaseModel):
    """GET /core/archivos/duplicados?hash=..."""
    model_config = ConfigDict(frozen=True)
    hash_sha256: str
    coincidencias: list[ArchivoDigitalResponse]
    total: int


class RetencionExecResult(BaseModel):
    """POST /core/archivos/aplicar-retencion."""
    model_config = ConfigDict(frozen=True)
    dry_run: bool
    candidatos_evaluados: int
    purgados: int
    saltados: int
    detalle: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    # Enums
    'StorageBackend', 'EstadoArchivo', 'AntivirusEstado',
    'Proposito', 'RetencionPolitica',
    # Requests
    'SubirArchivoMetadata', 'AttachPropositoRequest',
    'ReextraerRequest', 'AplicarRetencionRequest', 'AnularArchivoRequest',
    # Responses
    'ArchivoDigitalResponse', 'ArchivoListResponse',
    'DescargaArchivoResponse', 'ExtraccionResultadoResponse',
    'DuplicadosResponse', 'RetencionExecResult',
]
