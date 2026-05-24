"""Schemas Pydantic para GD-API-0012 — Estructura orgánica versionada.

Contratos en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 8.
"""
from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EstadoVersion = Literal['borrador', 'vigente', 'cerrada', 'historica']

EstadoDependencia = Literal['activa', 'inactiva', 'cerrada', 'fusionada']


# =============================================================================
# Versión de estructura orgánica
# =============================================================================

class VersionEstructuraCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    numero_version: str = Field(min_length=1, max_length=40)
    descripcion: str | None = Field(default=None, max_length=2000)
    acto_administrativo: str | None = Field(default=None, max_length=500)
    fecha_inicio_vigencia: date


class VersionEstructuraResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    numero_version: str
    descripcion: str | None = None
    acto_administrativo: str | None = None
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date | None = None
    estado: EstadoVersion
    dependencias_clonadas: int = 0


class VersionEstructuraVigenteResponse(BaseModel):
    """Response GET /api/v1/gd/estructura/vigente."""
    model_config = ConfigDict(frozen=True)

    version_estructura_id: UUID
    numero_version: str
    fecha_inicio_vigencia: date
    dependencias_count: int


# =============================================================================
# Dependencia
# =============================================================================

class DependenciaCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    codigo_organico: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=2, max_length=300)
    dependencia_padre_id: UUID | None = None
    fecha_inicio_vigencia: date
    version_estructura_id: UUID


class DependenciaPatch(BaseModel):
    """PATCH dependencia — solo nombre y dependencia_padre_id.

    Cambios estructurales (código_organico, fecha_inicio) requieren abrir
    nueva versión de estructura.
    """
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    nombre: str | None = Field(default=None, min_length=2, max_length=300)
    dependencia_padre_id: UUID | None = None


class DependenciaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    codigo_organico: str
    nombre: str
    dependencia_padre_id: UUID | None = None
    version_estructura_id: UUID
    estado: EstadoDependencia
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date | None = None


class DependenciaListResponse(BaseModel):
    """Response GET /api/v1/gd/dependencias (lista plana)."""
    model_config = ConfigDict(frozen=True)

    items: list[DependenciaResponse]


class DependenciaJerarquicaItem(BaseModel):
    """Item de árbol jerárquico (incluir_jerarquia=true)."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    codigo_organico: str
    nombre: str
    hijos: list['DependenciaJerarquicaItem'] = Field(default_factory=list)


class DependenciaJerarquicaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    raiz: list[DependenciaJerarquicaItem]


class DependenciaCerrarVigenciaRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    motivo: str = Field(min_length=10, max_length=500)
    fecha_fin: date
    acto_administrativo: str | None = Field(default=None, max_length=500)


__all__ = [
    'EstadoVersion',
    'EstadoDependencia',
    'VersionEstructuraCreate',
    'VersionEstructuraResponse',
    'VersionEstructuraVigenteResponse',
    'DependenciaCreate',
    'DependenciaPatch',
    'DependenciaResponse',
    'DependenciaListResponse',
    'DependenciaJerarquicaItem',
    'DependenciaJerarquicaResponse',
    'DependenciaCerrarVigenciaRequest',
]
