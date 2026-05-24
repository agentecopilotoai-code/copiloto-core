"""Schemas Pydantic para EP-021 periféricos parte 1 (bloque 21a).

Cubre GD-API-0128..0135:
- CRUD puntos de atención + periféricos
- Códigos de barras/QR por radicado
- Impresión etiqueta + reimpresión controlada + impresión constancia
- Digitalización individual
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Enums (Literal types alineados con CHECK constraints en SQL § 22)
# =============================================================================

TipoPeriferico = Literal[
    'impresora_etiquetas', 'impresora_termica', 'impresora_convencional',
    'escaner_plano', 'escaner_automatico', 'lector_codigo_barras', 'otro',
]
EstadoPeriferico = Literal['activo', 'inactivo', 'mantenimiento', 'retirado']
EstadoPunto = Literal['activo', 'inactivo', 'cerrado']
TipoCodigo = Literal['codigo_barras', 'qr', 'otro']
EstadoCodigo = Literal['activo', 'anulado', 'reemplazado']
TipoImpresion = Literal[
    'etiqueta_codigo_barras', 'etiqueta_qr', 'constancia_radicacion',
    'sello_documento', 'sticker', 'comprobante',
]
EstadoImpresion = Literal[
    'encolada', 'generada', 'fallida', 'anulada', 'reemplazada',
]
TipoDigitalizacion = Literal['plano', 'automatico', 'lote', 'individual']
EstadoDigitalizacion = Literal[
    'encolada', 'correcta', 'fallida', 'incompleta', 'reemplazada',
]
FormatoEtiqueta = Literal['estandar', 'compacta', 'sticker']
FormatoConstancia = Literal['estandar', 'compacta']


# =============================================================================
# Puntos de atención (GD-API-0130)
# =============================================================================

class CrearPuntoAtencionRequest(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    direccion: str | None = Field(default=None, max_length=500)
    dependencia_responsable_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchPuntoAtencionRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    direccion: str | None = Field(default=None, max_length=500)
    dependencia_responsable_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class CambiarEstadoPuntoRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)


class PuntoAtencionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    nombre: str
    direccion: str | None = None
    dependencia_responsable_id: UUID | None = None
    estado: str
    motivo_cierre: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Periféricos (GD-API-0129)
# =============================================================================

class CrearPerifericoRequest(BaseModel):
    tipo_periferico: TipoPeriferico
    nombre: str = Field(min_length=2, max_length=200)
    marca: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    serial: str = Field(min_length=1, max_length=200)
    dependencia_id: UUID | None = None
    punto_atencion_id: UUID | None = None
    configuracion: dict[str, Any] = Field(default_factory=dict)


class PatchPerifericoRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    marca: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    dependencia_id: UUID | None = None
    punto_atencion_id: UUID | None = None
    configuracion: dict[str, Any] | None = None


class CambiarEstadoPerifericoRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)
    forzar: bool = False


class PerifericoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_periferico: str
    nombre: str
    marca: str | None = None
    modelo: str | None = None
    serial: str
    dependencia_id: UUID | None = None
    punto_atencion_id: UUID | None = None
    estado: str
    motivo_cambio_estado: str | None = None
    configuracion: dict[str, Any] = Field(default_factory=dict)
    ultimo_handshake_en: datetime | None = None
    fecha_registro: datetime
    created_at: datetime
    updated_at: datetime


class PerifericoDetalleResponse(PerifericoResponse):
    """Detalle con últimas 10 operaciones (impresiones + digitalizaciones)."""
    ultimas_operaciones: list[dict[str, Any]] = Field(default_factory=list)


class PerifericoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[PerifericoResponse]
    total: int


# =============================================================================
# Códigos de barras / QR (GD-API-0131)
# =============================================================================

class GenerarCodigoBarrasRequest(BaseModel):
    tipo_codigo: TipoCodigo = 'qr'


class AnularCodigoBarrasRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)
    generar_reemplazo: bool = False
    tipo_codigo_reemplazo: TipoCodigo | None = None


class CodigoBarrasResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_codigo: str
    radicado_id: UUID | None = None
    documento_id: UUID | None = None
    expediente_id: UUID | None = None
    valor_codigo: str
    token_opaco: str
    estado: str
    reemplazado_por_id: UUID | None = None
    motivo_anulacion: str | None = None
    fecha_generacion: datetime
    created_at: datetime


# =============================================================================
# Impresión etiqueta (GD-API-0132/0133/0134)
# =============================================================================

class ImprimirEtiquetaRequest(BaseModel):
    radicado_id: UUID
    formato_etiqueta: FormatoEtiqueta = 'estandar'
    incluir_qr: bool = True
    incluir_codigo_barras: bool = True


class ReimprimirEtiquetaRequest(BaseModel):
    radicado_id: UUID
    motivo: str = Field(min_length=10, max_length=2000)
    impresion_original_id: UUID | None = None


class ImprimirConstanciaRequest(BaseModel):
    radicado_id: UUID
    formato: FormatoConstancia = 'estandar'
    incluir_qr: bool = True


class ReportarResultadoImpresionRequest(BaseModel):
    estado: Literal['generada', 'fallida']
    mensaje_error: str | None = Field(default=None, max_length=2000)
    latencia_ms: int | None = Field(default=None, ge=0, le=300_000)


class ImpresionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    radicado_id: UUID
    documento_id: UUID | None = None
    periferico_id: UUID
    usuario_id: UUID
    tipo_impresion: str
    formato: str | None = None
    estado: str
    mensaje_error: str | None = None
    latencia_ms: int | None = None
    motivo_reimpresion: str | None = None
    intentos_reimpresion: int
    impresion_original_id: UUID | None = None
    archivo_digital_id: UUID | None = None
    contenido_impreso: dict[str, Any] = Field(default_factory=dict)
    fecha_impresion: datetime
    created_at: datetime


# =============================================================================
# Digitalización (GD-API-0135)
# =============================================================================

class DigitalizarRequest(BaseModel):
    radicado_id: UUID
    tipo_digitalizacion: TipoDigitalizacion = 'individual'
    calidad_dpi: int = Field(default=300, ge=50, le=4800)
    observacion: str | None = Field(default=None, max_length=2000)


class ReportarResultadoDigitalizacionRequest(BaseModel):
    estado: Literal['correcta', 'fallida', 'incompleta']
    archivo_digital_id: UUID | None = None
    numero_paginas: int | None = Field(default=None, ge=0, le=10_000)
    mensaje_error: str | None = Field(default=None, max_length=2000)
    observacion: str | None = Field(default=None, max_length=2000)


class DigitalizacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    radicado_id: UUID | None = None
    documento_id: UUID | None = None
    archivo_digital_id: UUID | None = None
    periferico_id: UUID
    usuario_id: UUID
    tipo_digitalizacion: str
    numero_paginas: int | None = None
    calidad_dpi: int | None = None
    estado: str
    mensaje_error: str | None = None
    observacion: str | None = None
    lote_id: UUID | None = None
    fecha_digitalizacion: datetime
    created_at: datetime


__all__ = [
    # Enums (re-export como tipos)
    'TipoPeriferico', 'EstadoPeriferico', 'EstadoPunto',
    'TipoCodigo', 'EstadoCodigo', 'TipoImpresion', 'EstadoImpresion',
    'TipoDigitalizacion', 'EstadoDigitalizacion',
    'FormatoEtiqueta', 'FormatoConstancia',
    # Puntos de atención
    'CrearPuntoAtencionRequest', 'PatchPuntoAtencionRequest',
    'CambiarEstadoPuntoRequest', 'PuntoAtencionResponse',
    # Periféricos
    'CrearPerifericoRequest', 'PatchPerifericoRequest',
    'CambiarEstadoPerifericoRequest', 'PerifericoResponse',
    'PerifericoDetalleResponse', 'PerifericoListResponse',
    # Códigos
    'GenerarCodigoBarrasRequest', 'AnularCodigoBarrasRequest',
    'CodigoBarrasResponse',
    # Impresión
    'ImprimirEtiquetaRequest', 'ReimprimirEtiquetaRequest',
    'ImprimirConstanciaRequest', 'ReportarResultadoImpresionRequest',
    'ImpresionResponse',
    # Digitalización
    'DigitalizarRequest', 'ReportarResultadoDigitalizacionRequest',
    'DigitalizacionResponse',
]
