"""Schemas Pydantic para EP-001 — Identidad, acceso, roles y permisos.

Contratos de payload documentados en:
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# GET /api/v1/gd/me — response
# =============================================================================

class GdMeDependencia(BaseModel):
    """Dependencia institucional dentro de la respuesta de /me."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    codigo: str | None = None
    nombre: str | None = None


class GdMeCargo(BaseModel):
    """Cargo institucional dentro de la respuesta de /me."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    nombre: str | None = None


class GdMePerfilSection(BaseModel):
    """Sección 'perfil_gd' del response de /me."""
    model_config = ConfigDict(frozen=True)

    tipo_vinculacion: str
    estado_gd: str
    fecha_inicio_vinculacion: date | None = None
    fecha_fin_vinculacion: date | None = None
    ultimo_acceso: datetime | None = None


class GdMeRolVigente(BaseModel):
    """Cada rol GD vigente asignado al usuario."""
    model_config = ConfigDict(frozen=True)

    asignacion_alcance_id: UUID
    rol_codigo: str
    rol_nombre: str
    dependencia_id: UUID | None = None
    dependencia_nombre: str | None = None
    alcance: Literal['propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global']
    fecha_inicio: date
    fecha_fin: date | None = None


class GdMeResponse(BaseModel):
    """Response shape de `GET /api/v1/gd/me`.

    Match exacto del schema documentado en
    `integracion/INTEGRACION_E1_IDENTIDAD.md` sección 1.
    """
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str
    nombres: str = Field(description="Parte 'nombres' separada del display_name")
    apellidos: str = Field(description="Parte 'apellidos' separada del display_name")
    perfil_gd: GdMePerfilSection
    dependencia_actual: GdMeDependencia | None = None
    cargo_actual: GdMeCargo | None = None
    roles_gd_vigentes: list[GdMeRolVigente] = Field(default_factory=list)
    permisos_efectivos: list[str] = Field(
        default_factory=list,
        description='Lista plana de códigos de permiso efectivos para el usuario en este tenant.',
    )
    modulos_activos_organizacion: list[str] = Field(
        default_factory=list,
        description=(
            'Códigos de módulos activos según gd.organizacion_modulo_activacion. '
            'EP-002 los inserta; mientras EP-002 no esté implementado, este campo viene vacío '
            'y la UI debe asumir todos activos (modo fallback).'
        ),
    )


__all__ = [
    'GdMeDependencia',
    'GdMeCargo',
    'GdMePerfilSection',
    'GdMeRolVigente',
    'GdMeResponse',
]
