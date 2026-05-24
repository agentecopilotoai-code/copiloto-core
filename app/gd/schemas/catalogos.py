"""Schemas Pydantic para catálogos institucionales del bloque 4.

Cubre GD-API-0013 (cargos), GD-API-0014 (canales, calendarios, tipos PQRSD,
tipos correspondencia), GD-API-0016 (reglas comunicación).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EstadoActivoInactivo = Literal['activo', 'inactivo']
TipoDias = Literal['habiles', 'calendario']
AmbitoCorrespondencia = Literal['interna', 'externa_recibida', 'externa_enviada']
EstadoRegla = Literal['activa', 'inactiva']


# =============================================================================
# Cargos (GD-API-0013)
# =============================================================================

class CargoCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=200)
    dependencia_id: UUID | None = None
    fecha_inicio_vigencia: date | None = None  # default = today server-side


class CargoPatch(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    dependencia_id: UUID | None = None
    fecha_fin_vigencia: date | None = None


class CargoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    nombre: str
    dependencia_id: UUID | None = None
    estado: EstadoActivoInactivo
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date | None = None


class CargoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CargoResponse]


# =============================================================================
# Canales (GD-API-0014)
# =============================================================================

class CanalCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    codigo: str = Field(min_length=2, max_length=40)
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)
    requiere_punto_atencion: bool = False
    requiere_digitalizacion: bool = False
    permite_acuse: bool = True


class CanalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    requiere_punto_atencion: bool
    requiere_digitalizacion: bool
    permite_acuse: bool
    estado: EstadoActivoInactivo


class CanalListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CanalResponse]


# =============================================================================
# Calendarios (GD-API-0014)
# =============================================================================

class CalendarioCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=200)
    vigencia_anual: int = Field(ge=2020, le=2100)
    festivos: list[date] = Field(default_factory=list)
    dias_no_laborales: list[int] = Field(default_factory=lambda: [0, 6])
    es_default: bool = False


class CalendarioResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    nombre: str
    vigencia_anual: int
    festivos: list[date] = Field(default_factory=list)
    dias_no_laborales: list[int]
    es_default: bool
    estado: EstadoActivoInactivo


class CalendariosListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendario_default_id: UUID | None = None
    items: list[CalendarioResponse]


class CalcularFechaLimiteRequest(BaseModel):
    """Helper para calcular fecha_limite via función SQL desde la UI."""
    model_config = ConfigDict(frozen=True)

    fecha_base: datetime
    termino_dias: int = Field(ge=0)
    tipo_dias: TipoDias


class CalcularFechaLimiteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    fecha_base: datetime
    termino_dias: int
    tipo_dias: TipoDias
    fecha_limite: datetime


# =============================================================================
# Tipos PQRSD (GD-API-0014)
# =============================================================================

class TipoPqrsdCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    codigo: str = Field(min_length=2, max_length=40)
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)
    termino_dias: int = Field(ge=1, le=3650)
    tipo_dias: TipoDias
    requiere_respuesta: bool = True


class TipoPqrsdResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    termino_dias: int
    tipo_dias: TipoDias
    requiere_respuesta: bool
    estado: EstadoActivoInactivo


class TiposPqrsdListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[TipoPqrsdResponse]


# =============================================================================
# Tipos correspondencia (GD-API-0014)
# =============================================================================

class TipoCorrespondenciaCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    codigo: str = Field(min_length=2, max_length=40)
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)
    ambito: AmbitoCorrespondencia


class TipoCorrespondenciaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    ambito: AmbitoCorrespondencia
    estado: EstadoActivoInactivo


class TiposCorrespondenciaListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[TipoCorrespondenciaResponse]


# =============================================================================
# Reglas de comunicación (GD-API-0016)
# =============================================================================

class ReglaComunicacionCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    dependencia_origen_id: UUID
    dependencia_destino_id: UUID
    permitido: bool = True
    requiere_aprobacion_jefe: bool = False
    motivo_restriccion: str | None = Field(default=None, max_length=1000)


class ReglaComunicacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    dependencia_origen_id: UUID
    dependencia_destino_id: UUID
    permitido: bool
    requiere_aprobacion_jefe: bool
    motivo_restriccion: str | None = None
    estado: EstadoRegla


class ReglasComunicacionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ReglaComunicacionResponse]


class ValidacionComunicacionResponse(BaseModel):
    """Response GET /api/v1/gd/reglas/comunicacion/validar?origen=&destino="""
    model_config = ConfigDict(frozen=True)

    origen: UUID
    destino: UUID
    permitido: bool
    requiere_aprobacion_jefe: bool
    motivo: str | None = None
    tiene_regla_explicita: bool = Field(
        description='True si hay fila en gd.regla_comunicacion_interdependencia; '
                    'False si el resultado viene del default permisivo.',
    )


__all__ = [
    'EstadoActivoInactivo',
    'TipoDias',
    'AmbitoCorrespondencia',
    'EstadoRegla',
    'CargoCreate', 'CargoPatch', 'CargoResponse', 'CargoListResponse',
    'CanalCreate', 'CanalResponse', 'CanalListResponse',
    'CalendarioCreate', 'CalendarioResponse', 'CalendariosListResponse',
    'CalcularFechaLimiteRequest', 'CalcularFechaLimiteResponse',
    'TipoPqrsdCreate', 'TipoPqrsdResponse', 'TiposPqrsdListResponse',
    'TipoCorrespondenciaCreate', 'TipoCorrespondenciaResponse',
    'TiposCorrespondenciaListResponse',
    'ReglaComunicacionCreate', 'ReglaComunicacionResponse',
    'ReglasComunicacionListResponse', 'ValidacionComunicacionResponse',
]
