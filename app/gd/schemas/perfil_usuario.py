"""Schemas Pydantic para GD-API-0003 — Gestión institucional del perfil GD.

Contratos documentados en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 2.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


TipoVinculacion = Literal[
    'planta',
    'provisional',
    'ops',
    'supernumerario',
    'practicante',
    'externo_autorizado',
    'administrador_tecnico',
]

EstadoGd = Literal['activo', 'suspendido', 'inactivo', 'bloqueado', 'retirado']

AccionEstadoPerfil = Literal[
    'inactivar', 'bloquear', 'desbloquear', 'retirar', 'suspender'
]


class PerfilUsuarioCreate(BaseModel):
    """POST /api/v1/gd/perfil-usuario body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    user_id: UUID
    tipo_vinculacion: TipoVinculacion
    fecha_inicio_vinculacion: date
    fecha_fin_vinculacion: date | None = None
    dependencia_actual_id: UUID
    cargo_actual_id: UUID | None = None

    @field_validator('fecha_fin_vinculacion')
    @classmethod
    def _fecha_fin_posterior(
        cls, v: date | None, info
    ) -> date | None:
        if v is None:
            return v
        fecha_inicio = info.data.get('fecha_inicio_vinculacion')
        if fecha_inicio and v < fecha_inicio:
            raise ValueError('fecha_fin_vinculacion debe ser >= fecha_inicio_vinculacion')
        return v


class PerfilUsuarioPatch(BaseModel):
    """PATCH /api/v1/gd/perfil-usuario/{user_id} body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    tipo_vinculacion: TipoVinculacion | None = None
    fecha_fin_vinculacion: date | None = None
    dependencia_actual_id: UUID | None = None
    cargo_actual_id: UUID | None = None


class PerfilUsuarioCambioEstadoRequest(BaseModel):
    """Body común para POST .../{accion} con motivo obligatorio."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=500)


class PerfilUsuarioResponse(BaseModel):
    """Response para POST/PATCH/GET de un perfil."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    tenant_id: UUID
    perfil_id: UUID
    tipo_vinculacion: TipoVinculacion
    estado_gd: EstadoGd
    fecha_inicio_vinculacion: date
    fecha_fin_vinculacion: date | None = None
    dependencia_actual_id: UUID | None = None
    cargo_actual_id: UUID | None = None
    ultimo_acceso: datetime | None = None
    created_at: datetime
    created_by_user_id: UUID | None = None


class PerfilUsuarioCambioEstadoResponse(BaseModel):
    """Response del cambio de estado."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    estado_gd_anterior: EstadoGd
    estado_gd_nuevo: EstadoGd
    motivo: str
    ejecutado_por_user_id: UUID
    ejecutado_en: datetime


class PerfilUsuarioListItem(BaseModel):
    """Item de la lista paginada GET /api/v1/gd/perfil-usuario."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str
    nombres: str
    apellidos: str
    tipo_vinculacion: TipoVinculacion
    estado_gd: EstadoGd
    dependencia_actual_id: UUID | None = None
    cargo_actual_id: UUID | None = None
    roles_gd_count: int
    ultimo_acceso: datetime | None = None


class Paginacion(BaseModel):
    """Wrapper estándar de paginación cursor-based."""
    model_config = ConfigDict(frozen=True)

    siguiente_cursor: str | None = None
    total_estimado: int
    limit_aplicado: int


class PerfilUsuarioListResponse(BaseModel):
    """Response paginada de listar perfiles."""
    model_config = ConfigDict(frozen=True)

    items: list[PerfilUsuarioListItem]
    pagina: Paginacion


class PerfilUsuarioHistorialEvento(BaseModel):
    """Item del historial de un perfil (eventos auditables)."""
    model_config = ConfigDict(frozen=True)

    evento_auditoria_id: UUID
    tipo_evento: str
    accion: str
    valor_anterior: dict | None = None
    valor_nuevo: dict | None = None
    ejecutado_por_user_id: UUID | None = None
    ejecutado_por_nombre: str | None = None
    motivo: str | None = None
    fecha: datetime


class PerfilUsuarioHistorialResponse(BaseModel):
    """Response GET /api/v1/gd/perfil-usuario/{user_id}/historial."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    eventos: list[PerfilUsuarioHistorialEvento]


__all__ = [
    'TipoVinculacion',
    'EstadoGd',
    'AccionEstadoPerfil',
    'PerfilUsuarioCreate',
    'PerfilUsuarioPatch',
    'PerfilUsuarioCambioEstadoRequest',
    'PerfilUsuarioResponse',
    'PerfilUsuarioCambioEstadoResponse',
    'PerfilUsuarioListItem',
    'PerfilUsuarioListResponse',
    'PerfilUsuarioHistorialEvento',
    'PerfilUsuarioHistorialResponse',
    'Paginacion',
]
