"""Schemas Pydantic para EP-014 reportes e indicadores (bloque 15)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoReporte = Literal[
    'radicados', 'pqrsd', 'correspondencia',
    'cargas_trabajo', 'uso_ia', 'anulaciones_reasignaciones',
    'auditoria_consultas_sensibles',
]
FormatoReporte = Literal['json', 'csv', 'excel', 'pdf']
EstadoReporte = Literal['pending', 'processing', 'completed', 'failed']


# =============================================================================
# Filtros base reutilizables
# =============================================================================

class FiltrosFecha(BaseModel):
    """Filtro de rango de fechas común a todos los reportes."""
    desde: datetime | None = None
    hasta: datetime | None = None


# =============================================================================
# Requests (GD-API-0087..0093)
# =============================================================================

class ReporteRadicadosFiltros(FiltrosFecha):
    """GD-API-0087."""
    canal_id: UUID | None = None
    dependencia_id: UUID | None = None
    tipo_radicado: Literal['entrada', 'salida', 'interno'] | None = None
    estado: str | None = None


class ReportePqrsdFiltros(FiltrosFecha):
    """GD-API-0088."""
    dependencia_id: UUID | None = None
    tipo_pqrsd_id: UUID | None = None
    estado: str | None = None
    solo_vencidas: bool = False
    solo_proximas_vencer: bool = False


class ReporteCorrespondenciaFiltros(FiltrosFecha):
    """GD-API-0089."""
    tipo: Literal['interna', 'externa_recibida', 'externa_enviada'] | None = None
    dependencia_id: UUID | None = None
    estado: str | None = None


class ReporteCargasFiltros(FiltrosFecha):
    """GD-API-0090."""
    dependencia_id: UUID | None = None
    user_id: UUID | None = None


class ReporteUsoIAFiltros(FiltrosFecha):
    """GD-API-0091."""
    tipo_asistencia: str | None = None


class ReporteAnulacionesFiltros(FiltrosFecha):
    """GD-API-0092."""
    tipo_entidad: Literal['radicado', 'documento', 'pqrsd', 'correspondencia'] | None = None
    decision: Literal['pendiente', 'aprobada', 'rechazada'] | None = None


class ReporteAuditoriaFiltros(FiltrosFecha):
    """GD-API-0093 — consultas a información sensible."""
    usuario_id: UUID | None = None
    entidad_tipo: str | None = None


class ExportarRequest(BaseModel):
    """Wrapper para POST /reportes/.../exportar?formato=...
    Acepta filtros del reporte + flag de inclusión de datos sensibles.
    """
    formato: FormatoReporte = 'csv'
    filtros: dict[str, Any] = Field(default_factory=dict)
    incluir_datos_sensibles: bool = False


# =============================================================================
# Responses
# =============================================================================

class ReporteRadicadosFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    fecha: str  # YYYY-MM-DD
    canal_id: UUID | None = None
    canal_nombre: str | None = None
    dependencia_id: UUID | None = None
    tipo_radicado: str
    estado: str
    total: int


class ReporteRadicadosResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_radicados: int
    filas: list[ReporteRadicadosFila]
    filtros_aplicados: dict[str, Any] = Field(default_factory=dict)


class ReportePqrsdFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    tipo_pqrsd_id: UUID | None = None
    dependencia_id: UUID | None = None
    estado: str
    total: int
    vencidas: int
    proximas_vencer: int
    dias_promedio_resolucion: float | None = None


class ReportePqrsdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_global: int
    total_vencidas: int
    total_proximas_vencer: int
    total_cerradas: int
    filas: list[ReportePqrsdFila]


class ReporteCorrespondenciaFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    tipo: str
    estado: str
    dependencia_id: UUID | None = None
    total: int


class ReporteCorrespondenciaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: int
    filas: list[ReporteCorrespondenciaFila]


class ReporteCargasFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: UUID | None = None
    dependencia_id: UUID | None = None
    tareas_pendientes: int
    tareas_completadas_periodo: int
    radicados_clasificados_periodo: int


class ReporteCargasResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    filas: list[ReporteCargasFila]


class ReporteUsoIAFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    tipo_asistencia: str
    total_solicitudes: int
    completadas: int
    failed: int
    aceptadas: int
    modificadas: int
    rechazadas: int
    sin_decision: int


class ReporteUsoIAResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    filas: list[ReporteUsoIAFila]
    total_solicitudes: int


class ReporteAnulacionesFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    tipo_entidad: str
    decision: str
    total: int


class ReporteAnulacionesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    filas: list[ReporteAnulacionesFila]


class ReporteAuditoriaFila(BaseModel):
    model_config = ConfigDict(frozen=True)
    fecha: str
    usuario_id: UUID | None = None
    accion: str
    entidad_tipo: str | None = None
    clasificacion: str | None = None
    total: int


class ReporteAuditoriaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: int
    filas: list[ReporteAuditoriaFila]


# =============================================================================
# Reporte generado (registro auditable)
# =============================================================================

class ReporteGeneradoResponse(BaseModel):
    """GD-API-0094: registro de cada export."""
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_reporte: TipoReporte
    parametros: dict[str, Any] = Field(default_factory=dict)
    formato: FormatoReporte
    archivo_digital_id: UUID | None = None
    resumen_inline: dict[str, Any] | None = None
    numero_filas: int | None = None
    contiene_datos_sensibles: bool
    estado: EstadoReporte
    error_texto: str | None = None
    generado_por_user_id: UUID
    inicio_en: datetime
    fin_en: datetime | None = None
    duracion_ms: int | None = None
    expira_en: datetime | None = None


class ReporteGeneradoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[ReporteGeneradoResponse]
    total: int


__all__ = [
    # Enums
    'TipoReporte', 'FormatoReporte', 'EstadoReporte',
    # Filtros / requests
    'FiltrosFecha',
    'ReporteRadicadosFiltros', 'ReportePqrsdFiltros',
    'ReporteCorrespondenciaFiltros', 'ReporteCargasFiltros',
    'ReporteUsoIAFiltros', 'ReporteAnulacionesFiltros',
    'ReporteAuditoriaFiltros',
    'ExportarRequest',
    # Filas
    'ReporteRadicadosFila', 'ReportePqrsdFila',
    'ReporteCorrespondenciaFila', 'ReporteCargasFila',
    'ReporteUsoIAFila', 'ReporteAnulacionesFila',
    'ReporteAuditoriaFila',
    # Responses agregados
    'ReporteRadicadosResponse', 'ReportePqrsdResponse',
    'ReporteCorrespondenciaResponse', 'ReporteCargasResponse',
    'ReporteUsoIAResponse', 'ReporteAnulacionesResponse',
    'ReporteAuditoriaResponse',
    # Registro
    'ReporteGeneradoResponse', 'ReporteGeneradoListResponse',
]
