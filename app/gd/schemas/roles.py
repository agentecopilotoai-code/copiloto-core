"""Schemas Pydantic para GD-API-0004 — CRUD de roles GD y matriz rol↔permiso.

Contratos en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 3.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Alcance = Literal['propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global']

EstadoRol = Literal['activo', 'inactivo']


class RolCreate(BaseModel):
    """POST /api/v1/gd/roles body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    codigo: str = Field(min_length=4, max_length=80)
    nombre: str = Field(min_length=3, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)

    @field_validator('codigo')
    @classmethod
    def _prefijo_gd(cls, v: str) -> str:
        # Roles custom DEBEN tener prefijo 'gd.' para evitar colisión con
        # los roles del producto principal (owner, admin, agent, etc.).
        if not v.startswith('gd.'):
            raise ValueError("codigo debe comenzar con 'gd.' (ej. 'gd.revisor_juridico')")
        return v


class RolPatch(BaseModel):
    """PATCH /api/v1/gd/roles/{codigo} body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    nombre: str | None = Field(default=None, min_length=3, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)


class RolResponse(BaseModel):
    """Item de listado o detalle de rol."""
    model_config = ConfigDict(frozen=True)

    codigo: str
    nombre: str
    descripcion: str | None = None
    es_sistema: bool
    estado: EstadoRol
    permisos_count: int = 0


class RolListResponse(BaseModel):
    """Response GET /api/v1/gd/roles (lista, sin paginación porque catálogo es pequeño)."""
    model_config = ConfigDict(frozen=True)

    items: list[RolResponse]


class RolInactivarRequest(BaseModel):
    """Body para POST /api/v1/gd/roles/{codigo}/inactivar."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=500)


class RolPermisoAddRequest(BaseModel):
    """Body para POST /api/v1/gd/roles/{codigo}/permisos."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    permiso_codigo: str = Field(min_length=4, max_length=80)
    alcance_default: Alcance


class RolPermisoResponse(BaseModel):
    """Response cuando se agrega un permiso a un rol."""
    model_config = ConfigDict(frozen=True)

    rol_codigo: str
    permiso_codigo: str
    alcance_default: Alcance
    agregado_en: datetime


class PermisoResponse(BaseModel):
    """Item de GET /api/v1/gd/permisos."""
    model_config = ConfigDict(frozen=True)

    codigo: str
    nombre: str
    modulo: str
    descripcion: str | None = None
    es_critico: bool
    estado: EstadoRol


class PermisoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PermisoResponse]


__all__ = [
    'Alcance',
    'EstadoRol',
    'RolCreate',
    'RolPatch',
    'RolResponse',
    'RolListResponse',
    'RolInactivarRequest',
    'RolPermisoAddRequest',
    'RolPermisoResponse',
    'PermisoResponse',
    'PermisoListResponse',
]
