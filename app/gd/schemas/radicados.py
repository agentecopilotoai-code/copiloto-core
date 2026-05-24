"""Schemas Pydantic para GD-API-0024..0029 — Radicado (corazón del módulo).

Contratos en docs/gestion documental/integracion/INTEGRACION_E2_VENTANILLA.md
sección A.1-A.5.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.gd.schemas.terceros import TerceroCreate


TipoRadicado = Literal['entrada', 'salida', 'interno', 'otro']

EstadoRadicado = Literal[
    'registrado', 'clasificado', 'en_gestion', 'cerrado', 'anulado',
]

TipoClasificacion = Literal[
    'pqrsd', 'correspondencia_externa', 'correspondencia_interna',
    'tramite', 'expediente',
]

EstadoClasificacion = Literal['vigente', 'reemplazada']

FuenteClasificacion = Literal['manual', 'ia_aceptada', 'regla_automatica']

DecisionAnulacion = Literal['pendiente', 'aprobada', 'rechazada']

TipoEntidadAnulacion = Literal['radicado', 'documento', 'pqrsd', 'correspondencia']


# =============================================================================
# POST radicado entrada
# =============================================================================

class ClasificacionSugerida(BaseModel):
    """Sub-objeto opcional dentro del POST radicado entrada."""
    model_config = ConfigDict(frozen=True)

    tipo_clasificacion: TipoClasificacion
    sub_tipo: str | None = None
    dependencia_destino_id: UUID | None = None


class AnexoEnRadicado(BaseModel):
    """Anexo dentro del POST radicado entrada."""
    model_config = ConfigDict(frozen=True)

    archivo_digital_id: UUID  # FK a core.archivo_digital (EP-018 — diferido)
    descripcion: str | None = Field(default=None, max_length=500)
    es_principal: bool = False


class RadicadoEntradaCreate(BaseModel):
    """POST /api/v1/gd/ventanilla/radicados/entrada body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    canal_id: UUID
    punto_atencion_id: UUID | None = None
    asunto: str = Field(min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=5000)
    # Tercero: ya existente O creación inline (excluyentes).
    tercero_id: UUID | None = None
    tercero_nuevo: TerceroCreate | None = None
    dependencia_origen_id: UUID | None = None
    anexos: list[AnexoEnRadicado] = Field(default_factory=list, max_length=50)
    clasificacion_sugerida: ClasificacionSugerida | None = None
    sugerencia_ia_id: UUID | None = None
    es_radicacion_externa_desde_dependencia: bool = False

    @model_validator(mode='after')
    def _validar_tercero(self):
        # tercero_id y tercero_nuevo son excluyentes. Sin ninguno solo si el
        # canal lo acepta (validación adicional contra DB en el handler).
        if self.tercero_id is not None and self.tercero_nuevo is not None:
            raise ValueError('tercero_id y tercero_nuevo son excluyentes')
        return self


# =============================================================================
# POST radicado salida
# =============================================================================

class RadicadoSalidaCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    radicado_entrada_relacionado_id: UUID | None = None
    asunto: str = Field(min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=5000)
    dependencia_origen_id: UUID
    tercero_destinatario_id: UUID | None = None
    tercero_destinatario_nuevo: TerceroCreate | None = None
    # FK a gd.documento (EP-009 diferido) — validamos solo formato por ahora.
    documento_principal_id: UUID | None = None
    anexos: list[AnexoEnRadicado] = Field(default_factory=list, max_length=50)
    canal_envio_id: UUID

    @model_validator(mode='after')
    def _validar_destinatario(self):
        if self.tercero_destinatario_id is not None and self.tercero_destinatario_nuevo is not None:
            raise ValueError('tercero_destinatario_id y tercero_destinatario_nuevo son excluyentes')
        return self


# =============================================================================
# Response radicado
# =============================================================================

class RadicadoCanalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str


class RadicadoTerceroSummary(BaseModel):
    """Información reducida del tercero (RNF-017 — enmascarado para usuarios sin alcance)."""
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_tercero: str
    tipo_documento: str | None = None
    numero_documento_enmascarado: str | None = None
    nombres_razon_social: str


class RadicadoConstancia(BaseModel):
    """Información de la constancia generada."""
    model_config = ConfigDict(frozen=True)
    codigo_verificacion: str
    url_publica: str
    qr_archivo_digital_id: UUID | None = None
    constancia_pdf_archivo_digital_id: UUID | None = None


class RadicadoActorSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    usuario_id: UUID
    nombre_completo: str | None = None
    rol_codigo: str | None = None
    dependencia_codigo: str | None = None
    cargo: str | None = None


class RadicadoCreatedResponse(BaseModel):
    """Response 201 de POST entrada/salida — shape rico."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    numero_radicado: str
    tipo_radicado: TipoRadicado
    fecha_radicacion: datetime
    canal: RadicadoCanalSummary
    punto_atencion: dict | None = None  # placeholder hasta EP-021
    asunto: str
    descripcion: str | None = None
    tercero: RadicadoTerceroSummary | None = None
    dependencia_origen: dict | None = None
    estado: EstadoRadicado
    anexos_count: int
    constancia: RadicadoConstancia
    actor_snapshot: RadicadoActorSnapshot
    creado_en: datetime


# =============================================================================
# Búsqueda + detalle
# =============================================================================

class RadicadoListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    numero_radicado: str
    tipo_radicado: TipoRadicado
    fecha_radicacion: datetime
    asunto: str
    estado: EstadoRadicado
    canal: RadicadoCanalSummary
    tercero: RadicadoTerceroSummary | None = None
    dependencia_destino: dict | None = None
    clasificacion_vigente: dict | None = None
    anexos_count: int = 0


class RadicadoPagina(BaseModel):
    model_config = ConfigDict(frozen=True)
    siguiente_cursor: str | None = None
    total_estimado: int
    limit_aplicado: int


class RadicadoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[RadicadoListItem]
    pagina: RadicadoPagina


class RadicadoDetalleResponse(BaseModel):
    """GET /api/v1/gd/ventanilla/radicados/{id}."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    numero_radicado: str
    tipo_radicado: TipoRadicado
    fecha_radicacion: datetime
    canal: RadicadoCanalSummary
    asunto: str
    descripcion: str | None = None
    tercero: RadicadoTerceroSummary | None = None
    dependencia_origen: dict | None = None
    dependencia_destino: dict | None = None
    actor_snapshot: RadicadoActorSnapshot | None = None
    estado: EstadoRadicado
    radicado_relacionado_id: UUID | None = None
    codigo_verificacion: str
    es_radicacion_contingencia: bool


# =============================================================================
# Clasificación
# =============================================================================

class ClasificarRadicadoRequest(BaseModel):
    """POST /api/v1/gd/ventanilla/radicados/{id}/clasificar body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    tipo_clasificacion: TipoClasificacion
    sub_tipo: str | None = Field(default=None, max_length=100)
    dependencia_destino_id: UUID | None = None
    tipo_pqrsd_id: UUID | None = None
    justificacion: str | None = Field(default=None, max_length=2000)
    sugerencia_ia_id: UUID | None = None

    @model_validator(mode='after')
    def _validar_pqrsd_requiere_tipo(self):
        if self.tipo_clasificacion == 'pqrsd' and self.tipo_pqrsd_id is None:
            raise ValueError(
                'tipo_clasificacion=pqrsd exige tipo_pqrsd_id'
            )
        return self


class ReclasificarRadicadoRequest(ClasificarRadicadoRequest):
    """Igual que ClasificarRadicadoRequest + motivo obligatorio."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=500)


class ClasificacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    radicado_id: UUID
    tipo_clasificacion: TipoClasificacion
    sub_tipo: str | None = None
    dependencia_destino_id: UUID | None = None
    tipo_pqrsd_id: UUID | None = None
    fuente: FuenteClasificacion
    clasificado_por_user_id: UUID
    fecha_clasificacion: datetime
    estado: EstadoClasificacion


class ClasificarResponse(BaseModel):
    """Response del POST clasificar — incluye recursos creados por handler."""
    model_config = ConfigDict(frozen=True)
    radicado_id: UUID
    clasificacion: ClasificacionResponse
    recursos_creados: dict = Field(
        default_factory=dict,
        description='ids de pqrsd/correspondencia/expediente creados por '
                    'side-effects (stubs hasta EP-007/EP-008/EP-016).',
    )
    evento_auditoria_id: UUID | None = None


# =============================================================================
# Anulación
# =============================================================================

class SolicitudAnulacionCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=20, max_length=1000)
    evidencia_archivo_digital_id: UUID | None = None


class SolicitudAnulacionDecisionRequest(BaseModel):
    """Body común para aprobar/rechazar."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    observacion_decision: str | None = Field(default=None, max_length=1000)


class SolicitudAnulacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    solicitud_id: UUID
    tipo_entidad: TipoEntidadAnulacion
    entidad_afectada_id: UUID
    solicitante_user_id: UUID
    motivo: str
    decision: DecisionAnulacion
    fecha_solicitud: datetime
    aprobador_user_id: UUID | None = None
    observacion_decision: str | None = None
    fecha_decision: datetime | None = None


class RadicadoAnuladoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    solicitud_id: UUID
    decision: DecisionAnulacion
    aprobador_user_id: UUID
    fecha_decision: datetime
    radicado: dict  # subset con id, numero_radicado, estado, anulado_en


__all__ = [
    'TipoRadicado', 'EstadoRadicado', 'TipoClasificacion',
    'EstadoClasificacion', 'FuenteClasificacion',
    'DecisionAnulacion', 'TipoEntidadAnulacion',
    'ClasificacionSugerida', 'AnexoEnRadicado',
    'RadicadoEntradaCreate', 'RadicadoSalidaCreate',
    'RadicadoCanalSummary', 'RadicadoTerceroSummary',
    'RadicadoConstancia', 'RadicadoActorSnapshot',
    'RadicadoCreatedResponse',
    'RadicadoListItem', 'RadicadoPagina', 'RadicadoListResponse',
    'RadicadoDetalleResponse',
    'ClasificarRadicadoRequest', 'ReclasificarRadicadoRequest',
    'ClasificacionResponse', 'ClasificarResponse',
    'SolicitudAnulacionCreate', 'SolicitudAnulacionDecisionRequest',
    'SolicitudAnulacionResponse', 'RadicadoAnuladoResponse',
]
