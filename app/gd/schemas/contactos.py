"""Schemas Pydantic para GD-API-0034 — Contactos múltiples de tercero."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoContacto = Literal['correo', 'telefono', 'celular', 'direccion']

EstadoContacto = Literal['activo', 'inactivo']


class ContactoTerceroCreate(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    tipo_contacto: TipoContacto
    valor: str = Field(min_length=2, max_length=500)
    es_principal: bool = False


class ContactoTerceroResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    tercero_id: UUID
    tipo_contacto: TipoContacto
    valor: str
    es_principal: bool
    estado: EstadoContacto


class ContactosListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[ContactoTerceroResponse]


class ContactoTerceroInactivarRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    motivo: str = Field(min_length=5, max_length=500)


# =============================================================================
# Historial de tercero (GD-API-0035)
# =============================================================================

class HistorialItemTercero(BaseModel):
    """Item del historial unificado de un tercero (radicado/pqrsd/correspondencia)."""
    model_config = ConfigDict(frozen=True)

    tipo: Literal['radicado', 'pqrsd', 'correspondencia']
    id: UUID
    identificador: str  # numero_radicado, numero PQRSD, etc.
    fecha: datetime
    asunto: str | None = None
    estado: str | None = None


class HistorialTerceroResponse(BaseModel):
    """Response GET /api/v1/gd/terceros/{id}/historial."""
    model_config = ConfigDict(frozen=True)

    tercero_id: UUID
    items: list[HistorialItemTercero]
    totales: dict = Field(
        default_factory=dict,
        description='Conteos por tipo: {radicados: N, pqrsd: M, correspondencia: K}',
    )


__all__ = [
    'TipoContacto', 'EstadoContacto',
    'ContactoTerceroCreate', 'ContactoTerceroResponse',
    'ContactosListResponse', 'ContactoTerceroInactivarRequest',
    'HistorialItemTercero', 'HistorialTerceroResponse',
]
