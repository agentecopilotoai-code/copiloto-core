"""Schemas Pydantic para GD-API-0008 (reasignación stub → real) +
GD-API-0036..0039 (modelo Tarea, buzón, acciones).

Bloque 6 reactivó `gd.tarea` real. Los stubs de GD-API-0008 ahora consumen
datos reales. Schemas previos se mantienen + se agregan nuevos para el
modelo completo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Prioridad = Literal['baja', 'normal', 'alta', 'urgente']


class TareaPendienteItem(BaseModel):
    """Item de tareas pendientes de un usuario que va a inactivarse."""
    model_config = ConfigDict(frozen=True)

    tarea_id: UUID
    tipo_tarea: str
    entidad_origen_tipo: str
    entidad_origen_id: UUID
    titulo: str
    fecha_limite: datetime | None = None
    prioridad: Prioridad = 'normal'
    dias_para_vencimiento: int | None = None


class TareasPendientesPorTipo(BaseModel):
    """Conteos agregados por tipo de tarea pendiente."""
    model_config = ConfigDict(frozen=True)

    pqrsd_asignadas: int = 0
    documentos_por_revisar: int = 0
    documentos_por_firmar: int = 0
    correspondencia_recibida: int = 0
    tareas_genericas: int = 0


class TareasPendientesResponse(BaseModel):
    """Response GET /api/v1/gd/perfil-usuario/{user_id}/tareas-pendientes."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    total_pendientes: int
    por_tipo: TareasPendientesPorTipo
    items: list[TareaPendienteItem] = Field(default_factory=list)


class ReasignacionTareasRequest(BaseModel):
    """POST /api/v1/gd/perfil-usuario/{user_id}/tareas/reasignar body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    tareas: list[UUID] = Field(min_length=1, max_length=500)
    user_destino_id: UUID
    motivo: str = Field(min_length=10, max_length=500)


class ReasignacionTareaResultadoItem(BaseModel):
    """Resultado individual de cada reasignación."""
    model_config = ConfigDict(frozen=True)

    tarea_id: UUID
    estado: Literal['reasignada', 'fallida']
    evento_auditoria_id: UUID | None = None
    error: str | None = None


class ReasignacionTareasResponse(BaseModel):
    """Response del POST reasignar (puede ser 200 o 207 multi-status)."""
    model_config = ConfigDict(frozen=True)

    reasignadas: int
    fallidas: int
    detalles: list[ReasignacionTareaResultadoItem] = Field(default_factory=list)


# =============================================================================
# GD-API-0036..0039 — Modelo Tarea completo
# =============================================================================

TipoTarea = Literal[
    'clasificar', 'proyectar', 'revisar', 'aprobar', 'firmar',
    'responder', 'radicar', 'leer', 'generica',
]

EntidadOrigenTipo = Literal[
    'pqrsd', 'correspondencia', 'documento', 'radicado', 'generica',
]

EstadoTarea = Literal[
    'pendiente', 'en_proceso', 'devuelta', 'finalizada',
    'vencida', 'reasignada', 'anulada',
]

AccionTarea = Literal['iniciar', 'devolver', 'finalizar', 'escalar', 'anular']


class TareaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    tipo_tarea: TipoTarea
    titulo: str
    descripcion: str | None = None
    entidad_origen_tipo: EntidadOrigenTipo | None = None
    entidad_origen_id: UUID | None = None
    asignado_a_user_id: UUID | None = None
    asignado_a_dependencia_id: UUID | None = None
    asignado_por_user_id: UUID | None = None
    fecha_asignacion: datetime
    fecha_limite: datetime | None = None
    prioridad: Prioridad
    estado: EstadoTarea


class TareasListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[TareaResponse]
    pagina: dict = Field(default_factory=dict)


class TareaCreate(BaseModel):
    """POST /api/v1/gd/tareas (admin-internal — el patrón principal es que
    los workers reactivos creen tareas vía eventos; este endpoint es para
    tareas genéricas creadas manualmente)."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    tipo_tarea: TipoTarea = 'generica'
    titulo: str = Field(min_length=3, max_length=300)
    descripcion: str | None = Field(default=None, max_length=2000)
    entidad_origen_tipo: EntidadOrigenTipo | None = None
    entidad_origen_id: UUID | None = None
    asignado_a_user_id: UUID | None = None
    asignado_a_dependencia_id: UUID | None = None
    fecha_limite: datetime | None = None
    prioridad: Prioridad = 'normal'

    def _asignacion_xor(self):
        if (self.asignado_a_user_id is None
                and self.asignado_a_dependencia_id is None):
            raise ValueError('Debe asignarse a un usuario o una dependencia')
        return self


class TareaAccionRequest(BaseModel):
    """Body común para POST /tareas/{id}/{accion}."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    observacion: str | None = Field(default=None, max_length=2000)


class TareaReasignarRequest(BaseModel):
    """POST /api/v1/gd/tareas/{id}/reasignar body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    usuario_destino_id: UUID | None = None
    dependencia_destino_id: UUID | None = None
    motivo: str = Field(min_length=10, max_length=500)


# =============================================================================
# Buzón agregado (GD-API-0038)
# =============================================================================

class BuzonContador(BaseModel):
    """Contador + primera página de cada sección del buzón."""
    model_config = ConfigDict(frozen=True)
    total: int = 0
    items: list[TareaResponse] = Field(default_factory=list)


class BuzonResponse(BaseModel):
    """Response GET /api/v1/gd/buzon — agregado del usuario."""
    model_config = ConfigDict(frozen=True)

    usuario_id: UUID
    tareas_pendientes: BuzonContador = Field(default_factory=BuzonContador)
    tareas_en_proceso: BuzonContador = Field(default_factory=BuzonContador)
    tareas_devueltas: BuzonContador = Field(default_factory=BuzonContador)
    vencimientos_proximos: BuzonContador = Field(default_factory=BuzonContador)
    notificaciones_no_leidas: int = 0
    alertas_activas: int = 0


class BuzonDependenciaCargaItem(BaseModel):
    """KPI por usuario dentro del buzón de dependencia."""
    model_config = ConfigDict(frozen=True)
    user_id: UUID
    pendientes: int = 0
    en_proceso: int = 0
    vencidas: int = 0


class BuzonDependenciaResponse(BaseModel):
    """Response GET /api/v1/gd/buzon/dependencia/{id}."""
    model_config = ConfigDict(frozen=True)

    dependencia_id: UUID
    totales: dict = Field(default_factory=dict)
    carga_por_usuario: list[BuzonDependenciaCargaItem] = Field(default_factory=list)
    tareas_pendientes: BuzonContador = Field(default_factory=BuzonContador)


__all__ = [
    'Prioridad',
    'TareaPendienteItem',
    'TareasPendientesPorTipo',
    'TareasPendientesResponse',
    'ReasignacionTareasRequest',
    'ReasignacionTareaResultadoItem',
    'ReasignacionTareasResponse',
    # nuevos bloque 6
    'TipoTarea', 'EntidadOrigenTipo', 'EstadoTarea', 'AccionTarea',
    'TareaResponse', 'TareasListResponse', 'TareaCreate',
    'TareaAccionRequest', 'TareaReasignarRequest',
    'BuzonContador', 'BuzonResponse',
    'BuzonDependenciaCargaItem', 'BuzonDependenciaResponse',
]
