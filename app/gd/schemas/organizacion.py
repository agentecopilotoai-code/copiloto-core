"""Schemas Pydantic para GD-API-0011, 0011.b, 0011.c — Perfil organización.

Contratos en
docs/gestion documental/integracion/INTEGRACION_E1_IDENTIDAD.md sección 7.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TipoOrganizacion = Literal['publica', 'privada', 'mixta', 'ong', 'gremial', 'cooperativa']

TipoIdentificacionFiscal = Literal['NIT', 'RFC', 'CUIT', 'EIN', 'CNPJ', 'RUT', 'OTRO']

PoliticaFirmaDefault = Literal['escaneada', 'electronica', 'digital_certificada']

# 14 módulos activables — mantener sincronizado con el CHECK en
# infra/postgres/04-gd-schema.sql § 4.3.
ModuloActivable = Literal[
    'pqrsd_legal',
    'pqrsd_tickets',
    'correspondencia_interna',
    'correspondencia_externa',
    'firma_escaneada',
    'firma_electronica',
    'firma_digital_certificada',
    'expedientes',
    'trd_tvd',
    'integracion_correo',
    'agentes_ia',
    'radicacion_externa_desde_dependencia',
    'consulta_publica_radicado',
    'ventanilla_presencial_con_perifericos',
]


class PerfilOrganizacionLogo(BaseModel):
    """Logo de la organización (sub-objeto del response)."""
    model_config = ConfigDict(frozen=True)

    archivo_digital_id: UUID
    url_publica: str | None = None
    mime_type: str | None = None


class PerfilOrganizacionResponse(BaseModel):
    """Response GET /api/v1/gd/organizacion."""
    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    tipo_organizacion: TipoOrganizacion
    identificacion_fiscal: str
    tipo_identificacion_fiscal: TipoIdentificacionFiscal
    razon_social_legal: str
    nombre_corto: str
    direccion_oficial: str | None = None
    telefono_oficial: str | None = None
    correo_oficial: str | None = None
    sitio_web: str | None = None
    logo: PerfilOrganizacionLogo | None = None
    politica_firma_default: PoliticaFirmaDefault
    formato_radicado: str
    dias_alerta_vencimiento_default: int
    pais_iso: str
    zona_horaria_default: str


class PerfilOrganizacionCreate(BaseModel):
    """POST /api/v1/gd/organizacion body."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    tipo_organizacion: TipoOrganizacion
    identificacion_fiscal: str = Field(min_length=3, max_length=64)
    tipo_identificacion_fiscal: TipoIdentificacionFiscal = 'NIT'
    razon_social_legal: str = Field(min_length=3, max_length=300)
    nombre_corto: str = Field(min_length=2, max_length=120)
    direccion_oficial: str | None = Field(default=None, max_length=500)
    telefono_oficial: str | None = Field(default=None, max_length=50)
    correo_oficial: str | None = Field(default=None, max_length=200)
    sitio_web: str | None = Field(default=None, max_length=500)
    logo_archivo_digital_id: UUID | None = None
    politica_firma_default: PoliticaFirmaDefault = 'electronica'
    formato_radicado: str = '{prefijo}-{vigencia}-{consecutivo:06d}'
    dias_alerta_vencimiento_default: int = Field(default=3, ge=1, le=365)
    pais_iso: str = Field(default='CO', min_length=2, max_length=2)
    zona_horaria_default: str = 'America/Bogota'


class PerfilOrganizacionPatch(BaseModel):
    """PATCH /api/v1/gd/organizacion body.

    NOTA: `tipo_organizacion` no es editable después de crearse (cambiarlo
    requiere migración manual de defaults). Si necesitas cambiarlo, hacerlo
    directamente en SQL con justificación auditada.
    """
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    identificacion_fiscal: str | None = Field(default=None, min_length=3, max_length=64)
    tipo_identificacion_fiscal: TipoIdentificacionFiscal | None = None
    razon_social_legal: str | None = Field(default=None, min_length=3, max_length=300)
    nombre_corto: str | None = Field(default=None, min_length=2, max_length=120)
    direccion_oficial: str | None = Field(default=None, max_length=500)
    telefono_oficial: str | None = Field(default=None, max_length=50)
    correo_oficial: str | None = Field(default=None, max_length=200)
    sitio_web: str | None = Field(default=None, max_length=500)
    logo_archivo_digital_id: UUID | None = None
    politica_firma_default: PoliticaFirmaDefault | None = None
    formato_radicado: str | None = None
    dias_alerta_vencimiento_default: int | None = Field(default=None, ge=1, le=365)
    pais_iso: str | None = Field(default=None, min_length=2, max_length=2)
    zona_horaria_default: str | None = None


# =============================================================================
# Módulos activables (GD-API-0011.b)
# =============================================================================

class ModuloActivacionItem(BaseModel):
    """Un módulo + flag de activación + configuración opcional."""
    model_config = ConfigDict(frozen=True)

    modulo_codigo: ModuloActivable
    activado: bool
    configuracion: dict | None = None


class ModulosActivacionResponse(BaseModel):
    """Response GET /api/v1/gd/organizacion/modulos."""
    model_config = ConfigDict(frozen=True)

    modulos: list[ModuloActivacionItem]


class ModulosActivacionPatch(BaseModel):
    """PATCH /api/v1/gd/organizacion/modulos body."""
    model_config = ConfigDict(frozen=True, extra='forbid')

    modulos: list[ModuloActivacionItem] = Field(min_length=1, max_length=14)


__all__ = [
    'TipoOrganizacion',
    'TipoIdentificacionFiscal',
    'PoliticaFirmaDefault',
    'ModuloActivable',
    'PerfilOrganizacionLogo',
    'PerfilOrganizacionResponse',
    'PerfilOrganizacionCreate',
    'PerfilOrganizacionPatch',
    'ModuloActivacionItem',
    'ModulosActivacionResponse',
    'ModulosActivacionPatch',
]
