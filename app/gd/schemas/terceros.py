"""Schemas Pydantic para GD-API-0033 — Terceros."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


TipoTercero = Literal[
    'persona_natural', 'persona_juridica', 'entidad_publica',
    'entidad_privada', 'anonimo',
]

TipoDocumento = Literal['CC', 'CE', 'NIT', 'pasaporte', 'otro', 'sin_documento']

EstadoTercero = Literal['activo', 'inactivo']


class TerceroBase(BaseModel):
    """Campos comunes para crear/devolver tercero."""
    model_config = ConfigDict(str_strip_whitespace=True)

    tipo_tercero: TipoTercero
    tipo_documento: TipoDocumento | None = None
    numero_documento: str | None = Field(default=None, max_length=64)
    nombres_razon_social: str = Field(min_length=2, max_length=500)
    correo: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    direccion: str | None = Field(default=None, max_length=500)
    municipio: str | None = Field(default=None, max_length=100)
    departamento: str | None = Field(default=None, max_length=100)
    pais: str = Field(default='CO', min_length=2, max_length=2)

    @model_validator(mode='after')
    def _validar_documento(self):
        # Para no-anónimos exigimos tipo + número de documento.
        if self.tipo_tercero != 'anonimo':
            if not self.tipo_documento or self.tipo_documento == 'sin_documento':
                raise ValueError(
                    f'tipo_tercero={self.tipo_tercero!r} exige tipo_documento real'
                )
            if not self.numero_documento:
                raise ValueError(
                    f'tipo_tercero={self.tipo_tercero!r} exige numero_documento'
                )
        return self


class TerceroCreate(TerceroBase):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class TerceroPatch(BaseModel):
    """PATCH no permite cambiar tipo_documento ni numero_documento (para
    errores: anular y crear nuevo tercero)."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    nombres_razon_social: str | None = Field(default=None, min_length=2, max_length=500)
    correo: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    direccion: str | None = Field(default=None, max_length=500)
    municipio: str | None = Field(default=None, max_length=100)
    departamento: str | None = Field(default=None, max_length=100)
    pais: str | None = Field(default=None, min_length=2, max_length=2)


class TerceroResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    tipo_tercero: TipoTercero
    tipo_documento: TipoDocumento | None = None
    numero_documento: str | None = None
    nombres_razon_social: str
    correo: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    municipio: str | None = None
    departamento: str | None = None
    pais: str
    estado: EstadoTercero


class TerceroListItem(BaseModel):
    """Item de búsqueda de terceros (incluye score si vino de duplicados)."""
    model_config = ConfigDict(frozen=True)

    id: UUID
    tipo_tercero: TipoTercero
    tipo_documento: TipoDocumento | None = None
    numero_documento: str | None = None
    nombres_razon_social: str
    correo: str | None = None


class TerceroBusquedaResponse(BaseModel):
    """Response GET /api/v1/gd/terceros/buscar."""
    model_config = ConfigDict(frozen=True)

    items: list[TerceroListItem] = Field(default_factory=list)
    posibles_duplicados: list[TerceroListItem] = Field(default_factory=list)


__all__ = [
    'TipoTercero', 'TipoDocumento', 'EstadoTercero',
    'TerceroBase', 'TerceroCreate', 'TerceroPatch', 'TerceroResponse',
    'TerceroListItem', 'TerceroBusquedaResponse',
]
