"""Schemas Pydantic para EP-021 periféricos parte 2 (bloque 21b — cierre).

Cubre GD-API-0136..0142:
- Digitalización por lote (lote, finalizar, get progreso)
- Contexto activo (radicado activo por user+periférico)
- Mantenimiento + dashboard salud + eventos
- Registro/emparejamiento/revocación agente local
- Historial uso periféricos auditable + export
- Reemplazo digitalización (validación calidad)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ModoSeparacion = Literal['por_pagina', 'por_codigo_barras', 'manual']
EstadoLote = Literal['abierto', 'finalizado', 'abandonado']
TipoMantenimiento = Literal['preventivo', 'correctivo', 'auto_proteccion']
EstadoMantenimiento = Literal['en_curso', 'finalizado', 'cancelado']
EstadoAgente = Literal['pendiente', 'activo', 'revocado']
FormatoExport = Literal['csv', 'excel']


# =============================================================================
# Digitalización por lote (GD-API-0136)
# =============================================================================

class IniciarLoteRequest(BaseModel):
    modo_separacion: ModoSeparacion
    radicado_id_default: UUID | None = None
    calidad_dpi: int = Field(default=300, ge=50, le=4800)
    observacion: str | None = Field(default=None, max_length=2000)
    timeout_min: int = Field(default=30, ge=1, le=1440)


class FinalizarLoteRequest(BaseModel):
    observacion_final: str | None = Field(default=None, max_length=2000)


class LoteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    periferico_id: UUID
    usuario_id: UUID
    modo_separacion: str
    radicado_id_default: UUID | None = None
    estado: str
    calidad_dpi: int | None = None
    observacion: str | None = None
    total_documentos: int
    iniciado_en: datetime
    finalizado_en: datetime | None = None
    timeout_en: datetime | None = None


class LoteProgresoResponse(LoteResponse):
    """Progreso completo: lote + digitalizaciones asociadas."""
    digitalizaciones: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Contexto activo (GD-API-0137)
# =============================================================================

class ContextoActivoRequest(BaseModel):
    periferico_id: UUID
    radicado_activo_id: UUID
    expira_en_segundos: int = Field(default=300, ge=10, le=3600)


class ContextoActivoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    user_id: UUID
    periferico_id: UUID
    radicado_activo_id: UUID
    expira_en: datetime
    created_at: datetime


# =============================================================================
# Mantenimiento + eventos + dashboard (GD-API-0138)
# =============================================================================

class IniciarMantenimientoRequest(BaseModel):
    tipo: TipoMantenimiento = 'preventivo'
    descripcion: str = Field(min_length=5, max_length=2000)
    fecha_estimada_fin: date | None = None


class FinalizarMantenimientoRequest(BaseModel):
    observacion_final: str = Field(min_length=5, max_length=2000)
    costo: float | None = Field(default=None, ge=0)
    repuestos: list[dict[str, Any]] | None = None


class MantenimientoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    periferico_id: UUID
    tipo: str
    descripcion: str
    fecha_estimada_fin: date | None = None
    iniciado_por_user_id: UUID
    iniciado_en: datetime
    finalizado_en: datetime | None = None
    observacion_final: str | None = None
    costo: float | None = None
    repuestos: list[dict[str, Any]] | None = None
    finalizado_por_user_id: UUID | None = None
    estado: str


class EventoPerifericoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    periferico_id: UUID
    usuario_id: UUID | None = None
    tipo_evento: str
    entidad_relacionada_tipo: str | None = None
    entidad_relacionada_id: UUID | None = None
    resultado: str | None = None
    mensaje_error: str | None = None
    latencia_ms: int | None = None
    fecha_hora: datetime


class EventoPerifericoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[EventoPerifericoResponse]
    total: int


class FalloAgregadoItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    periferico_id: UUID
    periferico_nombre: str
    total_fallos: int
    ultimo_fallo: datetime | None = None


class FallosAgregadoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    desde: datetime
    items: list[FalloAgregadoItem]


# =============================================================================
# Agente local (GD-API-0139)
# =============================================================================

class EmparejarAgenteRequest(BaseModel):
    nombre_equipo: str = Field(min_length=2, max_length=200)
    version_agente: str | None = Field(default=None, max_length=80)
    perifericos: list[UUID] = Field(min_length=1, max_length=20)
    # base64 del fingerprint público (Ed25519/X25519/RSA).
    fingerprint_publico_b64: str = Field(min_length=10, max_length=4000)


class EmparejarAgenteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    agente_id: UUID
    nombre_equipo: str
    estado: str
    # Token one-shot devuelto en plano UNA sola vez (el hash queda en BD).
    token_emparejamiento: str
    token_expira_en: datetime
    perifericos: list[UUID] = Field(default_factory=list)


class RevocarAgenteRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)


class AgenteLocalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    nombre_equipo: str
    version_agente: str | None = None
    perifericos: list[UUID] = Field(default_factory=list)
    estado: str
    motivo_revocacion: str | None = None
    ultimo_handshake_en: datetime | None = None
    registrado_por_user_id: UUID
    fecha_registro: datetime


# =============================================================================
# Historial uso (GD-API-0141)
# =============================================================================

class HistorialOperacionItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tipo_operacion: Literal[
        'impresion', 'digitalizacion', 'evento_periferico',
    ]
    subtipo: str | None = None
    estado: str | None = None
    fecha: datetime
    usuario_id: UUID | None = None
    radicado_id: UUID | None = None
    mensaje_error: str | None = None


class HistorialResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[HistorialOperacionItem]
    total: int


class ExportHistorialRequest(BaseModel):
    formato: FormatoExport = 'csv'
    desde: datetime | None = None
    hasta: datetime | None = None
    periferico_id: UUID | None = None
    usuario_id: UUID | None = None


class ExportHistorialResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    export_id: UUID
    formato: str
    total_filas: int
    archivo_digital_id: UUID | None = None


# =============================================================================
# Reemplazo digitalización (GD-API-0142)
# =============================================================================

class ReemplazarDigitalizacionRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=2000)
    archivo_digital_id_nuevo: UUID


class ReemplazarDigitalizacionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    digitalizacion_original_id: UUID
    digitalizacion_nueva_id: UUID
    motivo: str
    fecha: datetime


__all__ = [
    # Enums
    'ModoSeparacion', 'EstadoLote', 'TipoMantenimiento',
    'EstadoMantenimiento', 'EstadoAgente', 'FormatoExport',
    # Lote
    'IniciarLoteRequest', 'FinalizarLoteRequest',
    'LoteResponse', 'LoteProgresoResponse',
    # Contexto
    'ContextoActivoRequest', 'ContextoActivoResponse',
    # Mantenimiento + eventos
    'IniciarMantenimientoRequest', 'FinalizarMantenimientoRequest',
    'MantenimientoResponse',
    'EventoPerifericoResponse', 'EventoPerifericoListResponse',
    'FalloAgregadoItem', 'FallosAgregadoResponse',
    # Agente
    'EmparejarAgenteRequest', 'EmparejarAgenteResponse',
    'RevocarAgenteRequest', 'AgenteLocalResponse',
    # Historial
    'HistorialOperacionItem', 'HistorialResponse',
    'ExportHistorialRequest', 'ExportHistorialResponse',
    # Reemplazo
    'ReemplazarDigitalizacionRequest', 'ReemplazarDigitalizacionResponse',
]
