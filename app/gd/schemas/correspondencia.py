"""Schemas Pydantic para EP-008 correspondencia interna/externa (bloque 9)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


TipoCorrespondencia = Literal['interna', 'externa_recibida', 'externa_enviada']

EstadoCorrespondencia = Literal[
    'borrador', 'enviada', 'leida', 'respondida', 'reenviada',
    'derivada', 'gestionada',
    'en_revision', 'devuelta', 'aprobada', 'firmada', 'radicada',
    'anulada',
]

PrioridadCorrespondencia = Literal['baja', 'normal', 'alta', 'urgente']

TipoDestinatario = Literal['dependencia', 'tercero']
TipoCopia = Literal['principal', 'copia', 'copia_oculta']


# =============================================================================
# Destinatarios (GD-API-0055)
# =============================================================================

class DestinatarioIn(BaseModel):
    """Item de entrada en arreglos `destinatarios=[...]` al crear correspondencia."""
    tipo_destinatario: TipoDestinatario
    dependencia_id: UUID | None = None
    tercero_id: UUID | None = None
    tipo_copia: TipoCopia = 'principal'

    @model_validator(mode='after')
    def _check_target(self):
        if self.tipo_destinatario == 'dependencia':
            if not self.dependencia_id or self.tercero_id:
                raise ValueError(
                    "tipo_destinatario='dependencia' requiere dependencia_id y NO tercero_id"
                )
        elif self.tipo_destinatario == 'tercero':
            if not self.tercero_id or self.dependencia_id:
                raise ValueError(
                    "tipo_destinatario='tercero' requiere tercero_id y NO dependencia_id"
                )
        return self


class DestinatarioResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    correspondencia_id: UUID
    tipo_destinatario: TipoDestinatario
    dependencia_id: UUID | None = None
    tercero_id: UUID | None = None
    tipo_copia: TipoCopia
    fecha_lectura: datetime | None = None
    leida_por_user_id: UUID | None = None


# =============================================================================
# Correspondencia interna (GD-API-0052)
# =============================================================================

class CrearInternaRequest(BaseModel):
    """POST /correspondencia/interna."""
    dependencia_origen_id: UUID
    asunto: str = Field(min_length=2, max_length=500)
    contenido_borrador: str | None = Field(default=None, max_length=20000)
    prioridad: PrioridadCorrespondencia = 'normal'
    requiere_respuesta: bool = False
    fecha_limite_respuesta: datetime | None = None
    documento_principal_id: UUID | None = None
    plantilla_id: UUID | None = None
    destinatarios: list[DestinatarioIn] = Field(min_length=1, max_length=50)
    enviar_inmediato: bool = True  # si false, queda en borrador

    @model_validator(mode='after')
    def _validate(self):
        # Todos los destinatarios deben ser dependencia (correspondencia interna).
        for d in self.destinatarios:
            if d.tipo_destinatario != 'dependencia':
                raise ValueError(
                    'En correspondencia interna todos los destinatarios deben ser tipo=dependencia'
                )
        return self


class ResponderRequest(BaseModel):
    """POST /correspondencia/{id}/responder."""
    dependencia_origen_id: UUID  # quién responde
    asunto: str = Field(min_length=2, max_length=500)
    contenido_borrador: str | None = Field(default=None, max_length=20000)
    documento_principal_id: UUID | None = None
    enviar_inmediato: bool = True


class ReenviarRequest(BaseModel):
    """POST /correspondencia/{id}/reenviar."""
    dependencia_origen_id: UUID  # quién reenvía
    destinatarios: list[DestinatarioIn] = Field(min_length=1, max_length=50)
    observaciones: str | None = Field(default=None, max_length=2000)


class MarcarLeidaRequest(BaseModel):
    """POST /correspondencia/{id}/marcar-leida."""
    dependencia_id: UUID  # qué dependencia marca leído


# =============================================================================
# Correspondencia externa enviada (GD-API-0054 — workflow)
# =============================================================================

class CrearExternaEnviadaBorrador(BaseModel):
    """POST /correspondencia/externa/borrador."""
    dependencia_origen_id: UUID
    asunto: str = Field(min_length=2, max_length=500)
    contenido_borrador: str | None = Field(default=None, max_length=20000)
    prioridad: PrioridadCorrespondencia = 'normal'
    documento_principal_id: UUID | None = None
    plantilla_id: UUID | None = None
    destinatarios: list[DestinatarioIn] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def _validate(self):
        # Externa enviada → al menos un destinatario tipo=tercero.
        terceros = [d for d in self.destinatarios if d.tipo_destinatario == 'tercero']
        if not terceros:
            raise ValueError(
                'Externa enviada debe incluir al menos un destinatario tipo=tercero'
            )
        return self


class EnviarRevisionInRequest(BaseModel):
    observaciones: str | None = Field(default=None, max_length=1000)


class RevisarCorrespondenciaRequest(BaseModel):
    resultado: Literal['ok', 'devolver']
    observaciones: str | None = Field(default=None, max_length=2000)


class AprobarCorrespondenciaRequest(BaseModel):
    observaciones: str | None = Field(default=None, max_length=1000)


class FirmarCorrespondenciaRequest(BaseModel):
    firma_id: UUID | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class RadicarSalidaCorrespondenciaRequest(BaseModel):
    canal_envio_id: UUID | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class EnviarCorrespondenciaRequest(BaseModel):
    canal_envio_id: UUID | None = None
    observaciones: str | None = Field(default=None, max_length=2000)


class RegistrarSoporteEnvioRequest(BaseModel):
    """POST /correspondencia/{id}/registrar-soporte-envio."""
    soporte_envio_uri: str = Field(min_length=2, max_length=1024)
    codigo_rastreo: str | None = Field(default=None, max_length=255)
    observaciones: str | None = Field(default=None, max_length=2000)


# =============================================================================
# Externa recibida (GD-API-0053)
# =============================================================================

class GestionarExternaRecibidaRequest(BaseModel):
    """POST /correspondencia/{id}/gestionar."""
    estado_destino: Literal['gestionada'] = 'gestionada'
    observaciones: str = Field(min_length=2, max_length=2000)
    dependencia_id: UUID | None = None  # opcional: re-asignar a otra dep


# =============================================================================
# Anulación (GD-API-0056)
# =============================================================================

class AnularCorrespondenciaRequest(BaseModel):
    """POST /correspondencia/{id}/anular."""
    motivo: str = Field(min_length=10, max_length=2000)
    evidencia_archivo_digital_id: UUID | None = None


class AprobarAnulacionCorrespRequest(BaseModel):
    """POST /correspondencia/solicitudes-anulacion/{id}/aprobar."""
    observacion: str | None = Field(default=None, max_length=2000)


class RechazarAnulacionCorrespRequest(BaseModel):
    """POST /correspondencia/solicitudes-anulacion/{id}/rechazar."""
    observacion: str = Field(min_length=5, max_length=2000)


# =============================================================================
# Response models
# =============================================================================

class CorrespondenciaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo: TipoCorrespondencia
    dependencia_origen_id: UUID | None = None
    dependencia_destino_id: UUID | None = None
    tercero_remitente_id: UUID | None = None
    radicado_entrada_id: UUID | None = None
    radicado_salida_id: UUID | None = None
    documento_principal_id: UUID | None = None
    plantilla_id: UUID | None = None
    asunto: str
    contenido_borrador: str | None = None
    prioridad: PrioridadCorrespondencia
    requiere_respuesta: bool
    fecha_limite_respuesta: datetime | None = None
    estado: EstadoCorrespondencia
    usuario_proyecta_id: UUID
    usuario_revisa_id: UUID | None = None
    usuario_aprueba_id: UUID | None = None
    usuario_firma_id: UUID | None = None
    usuario_envio_id: UUID | None = None
    fecha_envio: datetime | None = None
    fecha_aprobacion: datetime | None = None
    fecha_firma: datetime | None = None
    fecha_radicacion: datetime | None = None
    observaciones_devolucion: str | None = None
    canal_envio_id: UUID | None = None
    soporte_envio_uri: str | None = None
    soporte_envio_codigo_rastreo: str | None = None
    fecha_registro_soporte: datetime | None = None
    anulada_en: datetime | None = None
    motivo_anulacion: str | None = None
    correspondencia_padre_id: UUID | None = None
    created_at: datetime
    destinatarios: list[DestinatarioResponse] = Field(default_factory=list)


class CorrespondenciaListItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo: TipoCorrespondencia
    asunto: str
    estado: EstadoCorrespondencia
    prioridad: PrioridadCorrespondencia
    dependencia_origen_id: UUID | None = None
    dependencia_destino_id: UUID | None = None
    tercero_remitente_id: UUID | None = None
    fecha_envio: datetime | None = None
    requiere_respuesta: bool
    created_at: datetime


class CorrespondenciaListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[CorrespondenciaListItem]
    total: int


class SolicitudAnulacionCorrespResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_entidad: Literal['correspondencia']
    entidad_afectada_id: UUID
    solicitante_user_id: UUID
    motivo: str
    decision: Literal['pendiente', 'aprobada', 'rechazada']
    aprobador_user_id: UUID | None = None
    observacion_decision: str | None = None
    fecha_solicitud: datetime
    fecha_decision: datetime | None = None


__all__ = [
    # Enums
    'TipoCorrespondencia', 'EstadoCorrespondencia', 'PrioridadCorrespondencia',
    'TipoDestinatario', 'TipoCopia',
    # Destinatarios
    'DestinatarioIn', 'DestinatarioResponse',
    # Interna
    'CrearInternaRequest', 'ResponderRequest', 'ReenviarRequest',
    'MarcarLeidaRequest',
    # Externa enviada — workflow
    'CrearExternaEnviadaBorrador', 'EnviarRevisionInRequest',
    'RevisarCorrespondenciaRequest', 'AprobarCorrespondenciaRequest',
    'FirmarCorrespondenciaRequest', 'RadicarSalidaCorrespondenciaRequest',
    'EnviarCorrespondenciaRequest', 'RegistrarSoporteEnvioRequest',
    # Externa recibida
    'GestionarExternaRecibidaRequest',
    # Anulación
    'AnularCorrespondenciaRequest', 'AprobarAnulacionCorrespRequest',
    'RechazarAnulacionCorrespRequest',
    # Responses
    'CorrespondenciaResponse', 'CorrespondenciaListItem',
    'CorrespondenciaListResponse', 'SolicitudAnulacionCorrespResponse',
]
