"""Schemas Pydantic para EP-013 agentes IA asistidos (bloque 14)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoAsistencia = Literal[
    'clasificacion', 'extraccion', 'resumen', 'sugerencia_dependencia',
    'deteccion_duplicados', 'borrador_respuesta', 'sugerencia_termino',
]
EntidadOrigenIA = Literal[
    'radicado', 'pqrsd', 'correspondencia', 'documento', 'correo_importado',
]
EstadoSolicitudIA = Literal[
    'pending', 'processing', 'completed', 'failed', 'cancelled',
]
DecisionIA = Literal['aceptar', 'modificar', 'rechazar']


# =============================================================================
# Requests genéricos
# =============================================================================

class SolicitudIABase(BaseModel):
    """Base para todos los endpoints IA — entidad origen polimórfica."""
    entidad_origen_tipo: EntidadOrigenIA
    entidad_origen_id: UUID


class ClasificarRequest(SolicitudIABase):
    """POST /api/v1/gd/ia/clasificar — sugiere tipo_clasificacion para radicado."""
    # entidad_origen_tipo debe ser 'radicado' en práctica.
    pass


class ExtraerDatosRequest(SolicitudIABase):
    """POST /api/v1/gd/ia/extraer."""
    pass


class ResumirRequest(SolicitudIABase):
    """POST /api/v1/gd/ia/resumir."""
    max_caracteres: int = Field(default=500, ge=100, le=4000)


class SugerirDependenciaRequest(SolicitudIABase):
    pass


class DetectarDuplicadosRequest(SolicitudIABase):
    top_k: int = Field(default=5, ge=1, le=20)


class BorradorRespuestaRequest(SolicitudIABase):
    """POST /api/v1/gd/ia/borrador-respuesta — entidad debe ser pqrsd."""
    plantilla_id: UUID | None = None


class SugerirTerminoRequest(SolicitudIABase):
    pass


# =============================================================================
# Decisión humana (GD-API-0084)
# =============================================================================

class DecidirSugerenciaRequest(BaseModel):
    """POST /api/v1/gd/ia/sugerencias/{resultado_id}/decidir."""
    decision: DecisionIA
    contenido_modificado: dict[str, Any] | None = None
    observaciones: str | None = Field(default=None, max_length=2000)


# =============================================================================
# Responses
# =============================================================================

class SolicitudIAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_asistencia: TipoAsistencia
    entidad_origen_tipo: EntidadOrigenIA
    entidad_origen_id: UUID
    estado: EstadoSolicitudIA
    payload_original: dict[str, Any] = Field(default_factory=dict)
    datos_redactados: dict[str, Any] = Field(default_factory=dict)
    redacciones_aplicadas: list[dict[str, Any]] = Field(default_factory=list)
    proveedor: str | None = None
    error_texto: str | None = None
    error_codigo: str | None = None
    solicitante_user_id: UUID
    inicio_procesamiento_en: datetime | None = None
    fin_procesamiento_en: datetime | None = None
    created_at: datetime


class ResultadoIAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    solicitud_id: UUID
    contenido: dict[str, Any]
    confianza: float | None = None
    explicacion: str | None = None
    modelo: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    timing_ms: int | None = None
    created_at: datetime


class DecisionIAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    resultado_id: UUID
    decision: DecisionIA
    contenido_modificado: dict[str, Any] | None = None
    observaciones: str | None = None
    decided_by_user_id: UUID
    decided_at: datetime
    materializado_endpoint: str | None = None
    materializado_entidad_id: UUID | None = None


class SolicitudIACompleta(BaseModel):
    """Combina solicitud + resultado + decisión (si existen)."""
    model_config = ConfigDict(frozen=True)
    solicitud: SolicitudIAResponse
    resultado: ResultadoIAResponse | None = None
    decision: DecisionIAResponse | None = None


class TrazabilidadIAResponse(BaseModel):
    """GET /api/v1/gd/ia/trazabilidad (GD-API-0085)."""
    model_config = ConfigDict(frozen=True)
    entidad_origen_tipo: EntidadOrigenIA
    entidad_origen_id: UUID
    historial: list[SolicitudIACompleta]
    total: int


class RedaccionInfo(BaseModel):
    """Metadatos de una redacción aplicada por el minimizer."""
    model_config = ConfigDict(frozen=True)
    tipo: Literal['cedula', 'telefono', 'email', 'tarjeta', 'numero_documento']
    cantidad: int
    placeholder: str


__all__ = [
    # Enums
    'TipoAsistencia', 'EntidadOrigenIA', 'EstadoSolicitudIA', 'DecisionIA',
    # Requests
    'SolicitudIABase',
    'ClasificarRequest', 'ExtraerDatosRequest', 'ResumirRequest',
    'SugerirDependenciaRequest', 'DetectarDuplicadosRequest',
    'BorradorRespuestaRequest', 'SugerirTerminoRequest',
    'DecidirSugerenciaRequest',
    # Responses
    'SolicitudIAResponse', 'ResultadoIAResponse', 'DecisionIAResponse',
    'SolicitudIACompleta', 'TrazabilidadIAResponse', 'RedaccionInfo',
]
