"""Schemas Pydantic para EP-007 PQRSD — bloque 7 (GD-API-0042..0046)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EstadoPqrsd = Literal[
    'nueva', 'clasificada', 'asignada', 'en_analisis', 'en_revision',
    'devuelta', 'aprobada', 'firmada', 'enviada', 'cerrada',
    'trasladada', 'vencida', 'anulada',
]

PrioridadPqrsd = Literal['baja', 'normal', 'alta', 'urgente']

EstadoAsignacionPqrsd = Literal['activa', 'cerrada', 'reasignada']

EstadoRespuesta = Literal[
    'borrador', 'en_revision', 'devuelta', 'aprobada',
    'firmada', 'radicada', 'enviada',
]

TipoEventoTermino = Literal[
    'suspension', 'reanudacion', 'ampliacion',
    'solicitud_info_adicional', 'traslado_competencia',
]


class PqrsdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    radicado_entrada_id: UUID
    tipo_pqrsd_id: UUID | None = None
    tercero_id: UUID | None = None
    asunto: str
    descripcion: str | None = None
    dependencia_responsable_id: UUID | None = None
    usuario_responsable_id: UUID | None = None
    fecha_recepcion: datetime
    fecha_limite_respuesta: datetime | None = None
    estado: EstadoPqrsd
    prioridad: PrioridadPqrsd
    reserva: bool


class PqrsdListItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    radicado_entrada_id: UUID
    numero_radicado: str | None = None
    asunto: str
    estado: EstadoPqrsd
    fecha_recepcion: datetime
    fecha_limite_respuesta: datetime | None = None
    dependencia_responsable_id: UUID | None = None
    usuario_responsable_id: UUID | None = None
    dias_para_vencimiento: int | None = None
    semaforo: Literal['verde', 'ambar', 'rojo', 'vencido'] = 'verde'


class PqrsdListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[PqrsdListItem]
    total: int = 0


# =============================================================================
# Asignación
# =============================================================================

class AsignarDependenciaRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    dependencia_id: UUID
    motivo: str | None = Field(default=None, max_length=500)


class AsignarFuncionarioRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    usuario_id: UUID
    motivo: str | None = Field(default=None, max_length=500)


class ReasignarPqrsdRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    dependencia_id: UUID | None = None
    usuario_id: UUID | None = None
    motivo: str = Field(min_length=10, max_length=500)


class AsignacionPqrsdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    pqrsd_id: UUID
    dependencia_id: UUID | None = None
    usuario_asignado_id: UUID | None = None
    asignado_por_user_id: UUID | None = None
    fecha_asignacion: datetime
    fecha_fin: datetime | None = None
    motivo: str | None = None
    estado: EstadoAsignacionPqrsd


# =============================================================================
# Respuesta
# =============================================================================

class ProyectarRespuestaRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    documento_id: UUID | None = None  # FK gd.documento (EP-009 diferido)
    plantilla_id: UUID | None = None  # FK gd.plantilla (EP-010 diferido)
    contenido_borrador: str | None = Field(default=None, max_length=50000)


class RespuestaPqrsdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    pqrsd_id: UUID
    documento_id: UUID | None = None
    plantilla_id: UUID | None = None
    contenido_borrador: str | None = None
    usuario_proyecta_id: UUID
    usuario_revisa_id: UUID | None = None
    usuario_aprueba_id: UUID | None = None
    usuario_firma_id: UUID | None = None
    radicado_salida_id: UUID | None = None
    estado: EstadoRespuesta
    fecha_proyeccion: datetime
    fecha_revision: datetime | None = None
    fecha_aprobacion: datetime | None = None
    fecha_firma: datetime | None = None
    fecha_radicacion: datetime | None = None
    fecha_envio: datetime | None = None


# =============================================================================
# Suspensión / reanudación (GD-API-0042)
# =============================================================================

class SuspenderTerminoRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=2000)
    justificacion_legal: str | None = Field(default=None, max_length=2000)
    dias_estimados_suspension: int | None = Field(default=None, ge=1, le=365)


class ReanudarTerminoRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    motivo: str = Field(min_length=10, max_length=2000)


class EventoTerminoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    pqrsd_id: UUID
    tipo_evento: TipoEventoTermino
    fecha_evento: datetime
    motivo: str
    justificacion_legal: str | None = None
    dias_afectados: int | None = None
    fecha_limite_anterior: datetime | None = None
    fecha_limite_nueva: datetime | None = None
    usuario_id: UUID


class HistorialTerminoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    pqrsd_id: UUID
    eventos: list[EventoTerminoResponse]
    fecha_limite_vigente: datetime | None = None


# =============================================================================
# BLOQUE 8 — EP-007 cierre (GD-API-0047..0051).
# =============================================================================

# --- GD-API-0047: workflow respuesta ---

class EnviarRevisionRequest(BaseModel):
    """Body para POST /respuestas/{id}/enviar-a-revision."""
    observaciones: str | None = Field(default=None, max_length=1000)


class RevisarRespuestaRequest(BaseModel):
    """Body para POST /respuestas/{id}/revisar.
    resultado='ok' → estado='aprobada'; 'devolver' → estado='devuelta'.
    """
    resultado: Literal['ok', 'devolver']
    observaciones: str | None = Field(default=None, max_length=2000)


class AprobarRespuestaRequest(BaseModel):
    """Body para POST /respuestas/{id}/aprobar."""
    observaciones: str | None = Field(default=None, max_length=1000)


class FirmarRespuestaRequest(BaseModel):
    """Body para POST /respuestas/{id}/firmar (delegado a EP-011)."""
    firma_id: UUID | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class RadicarSalidaRequest(BaseModel):
    """Body para POST /respuestas/{id}/radicar-salida."""
    canal_envio_id: UUID | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class EnviarRespuestaRequest(BaseModel):
    """Body para POST /respuestas/{id}/enviar."""
    canal_envio_id: UUID | None = None
    constancia_envio_uri: str | None = Field(default=None, max_length=1024)
    observaciones: str | None = Field(default=None, max_length=2000)


# --- GD-API-0048: cierre / reapertura ---

class CerrarPqrsdRequest(BaseModel):
    """Body para POST /pqrsd/{id}/cerrar."""
    motivo: str = Field(min_length=5, max_length=2000)
    forzar_sin_respuesta: bool = False  # true → cierre sin respuesta enviada


class ReabrirPqrsdRequest(BaseModel):
    """Body para POST /pqrsd/{id}/reabrir."""
    motivo: str = Field(min_length=10, max_length=2000)
    dias_adicionales: int = Field(default=15, ge=1, le=180)


# --- GD-API-0049: traslado por competencia ---

class TrasladarCompetenciaRequest(BaseModel):
    """Body para POST /pqrsd/{id}/trasladar-competencia."""
    entidad_competente_destino: str = Field(min_length=2, max_length=255)
    motivo: str = Field(min_length=10, max_length=2000)
    oficio_traslado_radicado_id: UUID | None = None  # radicado de oficio


# --- GD-API-0050: solicitud info adicional ---

class SolicitarInfoAdicionalRequest(BaseModel):
    """Body para POST /pqrsd/{id}/solicitar-info-adicional.
    Pausa el término registrando suspensión (vía gd.evento_termino_pqrsd).
    """
    motivo: str = Field(min_length=10, max_length=2000)
    informacion_solicitada: str = Field(min_length=10, max_length=4000)
    dias_estimados_suspension: int = Field(default=10, ge=1, le=90)


# --- GD-API-0051: dashboard ---

class DashboardPqrsdBucket(BaseModel):
    """Una celda agregada del dashboard."""
    model_config = ConfigDict(frozen=True)
    dependencia_id: UUID | None = None
    estado: EstadoPqrsd
    tipo_pqrsd_id: UUID | None = None
    total: int
    vencidas: int
    proximas_vencer: int
    dias_promedio_resolucion: float | None = None


class DashboardPqrsdResponse(BaseModel):
    """Respuesta agregada para GET /pqrsd/dashboard."""
    model_config = ConfigDict(frozen=True)
    total_global: int
    total_vencidas: int
    total_proximas_vencer: int
    total_cerradas: int
    buckets: list[DashboardPqrsdBucket]
    desde: datetime | None = None
    hasta: datetime | None = None
    dependencia_id_filtro: UUID | None = None


# --- Respuestas extendidas para workflow respuesta ---

class RespuestaPqrsdDetalleResponse(BaseModel):
    """Detalle ampliado de gd.respuesta_pqrsd con timestamps de workflow."""
    model_config = ConfigDict(frozen=True)
    id: UUID
    pqrsd_id: UUID
    documento_id: UUID | None = None
    plantilla_id: UUID | None = None
    contenido_borrador: str | None = None
    usuario_proyecta_id: UUID
    usuario_revisa_id: UUID | None = None
    usuario_aprueba_id: UUID | None = None
    usuario_firma_id: UUID | None = None
    radicado_salida_id: UUID | None = None
    estado: EstadoRespuesta
    fecha_proyeccion: datetime
    fecha_revision: datetime | None = None
    fecha_aprobacion: datetime | None = None
    fecha_firma: datetime | None = None
    fecha_radicacion: datetime | None = None
    fecha_envio: datetime | None = None
    observaciones_devolucion: str | None = None


__all__ = [
    'EstadoPqrsd', 'PrioridadPqrsd', 'EstadoAsignacionPqrsd',
    'EstadoRespuesta', 'TipoEventoTermino',
    'PqrsdResponse', 'PqrsdListItem', 'PqrsdListResponse',
    'AsignarDependenciaRequest', 'AsignarFuncionarioRequest',
    'ReasignarPqrsdRequest', 'AsignacionPqrsdResponse',
    'ProyectarRespuestaRequest', 'RespuestaPqrsdResponse',
    'SuspenderTerminoRequest', 'ReanudarTerminoRequest',
    'EventoTerminoResponse', 'HistorialTerminoResponse',
    # bloque 8
    'EnviarRevisionRequest', 'RevisarRespuestaRequest',
    'AprobarRespuestaRequest', 'FirmarRespuestaRequest',
    'RadicarSalidaRequest', 'EnviarRespuestaRequest',
    'CerrarPqrsdRequest', 'ReabrirPqrsdRequest',
    'TrasladarCompetenciaRequest', 'SolicitarInfoAdicionalRequest',
    'DashboardPqrsdBucket', 'DashboardPqrsdResponse',
    'RespuestaPqrsdDetalleResponse',
]
