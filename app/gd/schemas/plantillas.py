"""Schemas Pydantic para EP-010 plantillas documentales (bloque 11)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoPlantilla = Literal[
    'oficio_respuesta', 'memorando_interno', 'constancia_radicacion',
    'traslado_competencia', 'solicitud_info_adicional',
    'respuesta_pqrsd', 'comunicacion_externa_salida', 'otra',
]

EstadoPlantilla = Literal['borrador', 'activa', 'inactiva']
EstadoVersionPlantilla = Literal[
    'borrador', 'activa', 'reemplazada', 'descartada',
]

AsociacionTipo = Literal['dependencia', 'tipo_tramite']


# =============================================================================
# Requests — CRUD plantilla
# =============================================================================

class CrearPlantillaRequest(BaseModel):
    codigo: str = Field(min_length=2, max_length=80, pattern=r'^[A-Z0-9_]+$')
    nombre: str = Field(min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    tipo_plantilla: TipoPlantilla
    dependencia_propietaria_id: UUID | None = None
    es_institucional: bool = False
    # Primera versión (opcional — si se provee, se crea como 'borrador').
    contenido_template: str | None = Field(default=None, max_length=100_000)
    json_schema_campos: dict[str, Any] | None = None
    mime_type: str = 'text/plain'


class PatchPlantillaRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=255)
    descripcion: str | None = Field(default=None, max_length=2000)
    dependencia_propietaria_id: UUID | None = None
    # nota: tipo_plantilla NO se patchea (cambiarlo es destructivo).


class NuevaVersionPlantillaRequest(BaseModel):
    contenido_template: str = Field(min_length=1, max_length=100_000)
    json_schema_campos: dict[str, Any] | None = None
    archivo_digital_id: UUID | None = None
    mime_type: str = 'text/plain'
    notas: str | None = Field(default=None, max_length=2000)


class ActivarPlantillaRequest(BaseModel):
    """Body para POST /plantillas/{id}/activar.

    Si version_id se pasa, esa versión se vuelve activa; si no, se usa la
    última en estado 'borrador'.
    """
    version_id: UUID | None = None


# =============================================================================
# Generar documento desde plantilla (GD-API-0065)
# =============================================================================

class GenerarDocumentoRequest(BaseModel):
    """POST /plantillas/{id}/generar-documento."""
    # Contexto opcional (al menos uno suele estar presente).
    radicado_id: UUID | None = None
    pqrsd_id: UUID | None = None
    correspondencia_id: UUID | None = None
    # Override / extra fields para el render del template.
    datos_adicionales: dict[str, Any] = Field(default_factory=dict)
    # Metadata del documento generado.
    titulo: str | None = Field(default=None, min_length=2, max_length=500)
    clasificacion_informacion: Literal[
        'publica', 'interna', 'reservada', 'confidencial',
        'datos_personales', 'sensible',
    ] = 'interna'


# =============================================================================
# Asociaciones (GD-API-0066)
# =============================================================================

class AsociarDependenciaRequest(BaseModel):
    """Body opcional para POST /plantillas/{id}/asociar-dependencia/{dep_id}."""
    pass


class AsociarTipoTramiteRequest(BaseModel):
    """Body para POST /plantillas/{id}/asociar-tipo-tramite/{tipo}.

    tipo se pasa como path param; aquí solo permitimos notas opcionales.
    """
    pass


# =============================================================================
# Responses
# =============================================================================

class VersionPlantillaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    plantilla_id: UUID
    numero_version: int
    contenido_template: str
    archivo_digital_id: UUID | None = None
    mime_type: str
    json_schema_campos: dict[str, Any]
    estado: EstadoVersionPlantilla
    notas: str | None = None
    created_by_user_id: UUID
    created_at: datetime


class PlantillaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    tipo_plantilla: TipoPlantilla
    estado: EstadoPlantilla
    version_vigente_id: UUID | None = None
    numero_version_vigente: int
    dependencia_propietaria_id: UUID | None = None
    es_institucional: bool
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    versiones: list[VersionPlantillaResponse] = Field(default_factory=list)


class PlantillaListItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    codigo: str
    nombre: str
    tipo_plantilla: TipoPlantilla
    estado: EstadoPlantilla
    numero_version_vigente: int
    dependencia_propietaria_id: UUID | None = None
    es_institucional: bool
    created_at: datetime


class PlantillaListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[PlantillaListItem]
    total: int


class AsociacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    plantilla_id: UUID
    asociacion_tipo: AsociacionTipo
    asociacion_id: UUID | None = None
    asociacion_codigo: str | None = None
    creado_por_user_id: UUID
    created_at: datetime


class GenerarDocumentoResponse(BaseModel):
    """Devuelve el documento_id creado + contenido renderizado."""
    model_config = ConfigDict(frozen=True)
    documento_id: UUID
    version_documento_id: UUID
    plantilla_id: UUID
    plantilla_version_id: UUID
    contenido_renderizado: str
    variables_usadas: dict[str, Any]


class SeedInstitucionalResponse(BaseModel):
    """POST /plantillas/_seed-institucionales."""
    model_config = ConfigDict(frozen=True)
    plantillas_creadas: list[UUID]
    plantillas_existentes: list[str]  # codigos que ya existían (no recreadas)
    total: int


__all__ = [
    # Enums
    'TipoPlantilla', 'EstadoPlantilla', 'EstadoVersionPlantilla',
    'AsociacionTipo',
    # Requests
    'CrearPlantillaRequest', 'PatchPlantillaRequest',
    'NuevaVersionPlantillaRequest', 'ActivarPlantillaRequest',
    'GenerarDocumentoRequest',
    'AsociarDependenciaRequest', 'AsociarTipoTramiteRequest',
    # Responses
    'PlantillaResponse', 'VersionPlantillaResponse',
    'PlantillaListItem', 'PlantillaListResponse',
    'AsociacionResponse', 'GenerarDocumentoResponse',
    'SeedInstitucionalResponse',
]
