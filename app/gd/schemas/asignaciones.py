"""Schemas Pydantic para GD-API-0005 — Asignación rol con alcance.

Contratos en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 4.

Importante (D9): los roles GD viven SOLO en `gd.asignacion_alcance`, no en
`app.user_tenant_roles`. La asignación es de una sola tabla.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.gd.schemas.roles import Alcance


EstadoAsignacion = Literal['activa', 'cerrada']


class AsignacionRolCreate(BaseModel):
    """POST /api/v1/gd/usuarios/{user_id}/roles body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    rol_codigo: str = Field(min_length=4, max_length=80)
    dependencia_id: UUID | None = None
    alcance: Alcance
    fecha_inicio: date
    fecha_fin: date | None = None
    motivo: str = Field(min_length=10, max_length=500)

    @field_validator('fecha_fin')
    @classmethod
    def _fecha_fin_posterior(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        inicio = info.data.get('fecha_inicio')
        if inicio and v < inicio:
            raise ValueError('fecha_fin debe ser >= fecha_inicio')
        return v

    @model_validator(mode='after')
    def _dependencia_requerida_segun_alcance(self):
        # Si el alcance es 'dependencia' o 'dependencias_autorizadas', se exige
        # dependencia_id explícita. 'propio', 'institucional', 'global' no.
        # Usamos model_validator(mode='after') porque field_validator no puede
        # leer otros campos cuando dependencia_id se declara ANTES que alcance.
        if self.alcance in ('dependencia', 'dependencias_autorizadas') and self.dependencia_id is None:
            raise ValueError(
                f'dependencia_id es requerida cuando alcance es {self.alcance!r}'
            )
        return self


class AsignacionRolCerrarRequest(BaseModel):
    """POST /api/v1/gd/usuarios/{user_id}/roles/{id}/cerrar body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=500)


class AsignacionRolResponse(BaseModel):
    """Item de roles asignados a un usuario."""
    model_config = ConfigDict(frozen=True)

    asignacion_alcance_id: UUID
    user_id: UUID
    rol_codigo: str
    rol_nombre: str | None = None  # join opcional para conveniencia UI
    dependencia_id: UUID | None = None
    alcance: Alcance
    fecha_inicio: date
    fecha_fin: date | None = None
    estado: EstadoAsignacion
    asignado_por_user_id: UUID | None = None
    motivo: str | None = None


class AsignacionesUsuarioResponse(BaseModel):
    """Response GET /api/v1/gd/usuarios/{user_id}/roles."""
    model_config = ConfigDict(frozen=True)

    vigentes: list[AsignacionRolResponse]
    historicas: list[AsignacionRolResponse] = Field(default_factory=list)


class AsignacionRolCerradaResponse(BaseModel):
    """Response del cierre de asignación."""
    model_config = ConfigDict(frozen=True)

    asignacion_alcance_id: UUID
    fecha_fin: datetime
    estado: EstadoAsignacion


__all__ = [
    'EstadoAsignacion',
    'AsignacionRolCreate',
    'AsignacionRolCerrarRequest',
    'AsignacionRolResponse',
    'AsignacionesUsuarioResponse',
    'AsignacionRolCerradaResponse',
]
