"""Schemas Pydantic para EP-012 correo institucional (bloque 13)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ProveedorCorreo = Literal[
    'imap_generico', 'gmail_api', 'microsoft_graph', 'pop3',
]
EstadoBuzon = Literal['activa', 'inactiva', 'error_credenciales', 'error_red']
EstadoCorreoImportado = Literal[
    'pendiente', 'convertido_radicado', 'asociado_radicado',
    'descartado', 'error_conversion',
]


# =============================================================================
# Buzones (GD-API-0073)
# =============================================================================

class CrearBuzonRequest(BaseModel):
    """POST /api/v1/gd/correo/buzones."""
    nombre: str = Field(min_length=2, max_length=255)
    direccion_correo: str = Field(min_length=3, max_length=320,
                                    pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    proveedor: ProveedorCorreo
    dependencia_id: UUID | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    usar_tls: bool = True
    usuario_smtp: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    # CRITICAL: solo recibimos referencia al secret vault, NO la credencial.
    secret_vault_ref: str = Field(min_length=2, max_length=500)
    envio_acuse_recibido: bool = False
    plantilla_acuse_id: UUID | None = None


class PatchBuzonRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=255)
    dependencia_id: UUID | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    usar_tls: bool | None = None
    usuario_smtp: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] | None = None
    secret_vault_ref: str | None = Field(default=None, min_length=2, max_length=500)
    envio_acuse_recibido: bool | None = None
    plantilla_acuse_id: UUID | None = None
    estado: EstadoBuzon | None = None


class ProbarConexionRequest(BaseModel):
    """Solo dispara el provider stub.test_conexion()."""
    pass


class EjecutarWorkerRequest(BaseModel):
    """POST /api/v1/gd/correo/buzones/{id}/ejecutar-worker.

    Trigger manual del worker de lectura (GD-API-0074). En producción se
    ejecuta vía scheduler; este endpoint es para admin/debug.
    """
    max_correos: int = Field(default=50, ge=1, le=500)


class BuzonResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    nombre: str
    direccion_correo: str
    proveedor: ProveedorCorreo
    dependencia_id: UUID | None = None
    host: str | None = None
    port: int | None = None
    usar_tls: bool
    usuario_smtp: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret_vault_ref: str
    ultima_lectura_en: datetime | None = None
    envio_acuse_recibido: bool
    plantilla_acuse_id: UUID | None = None
    estado: EstadoBuzon
    ultimo_error_texto: str | None = None
    ultimo_error_en: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BuzonListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[BuzonResponse]
    total: int


# =============================================================================
# Correos importados (GD-API-0074, 0075)
# =============================================================================

class ConvertirCorreoRadicadoRequest(BaseModel):
    """POST /api/v1/gd/correo/{id}/convertir-a-radicado."""
    asunto_override: str | None = Field(default=None, min_length=2, max_length=500)
    descripcion: str | None = Field(default=None, max_length=4000)
    canal_id: UUID  # gd.canal de entrada
    tercero_id: UUID | None = None  # si ya existe
    crear_tercero: bool = False  # si true, crea tercero desde remitente
    dependencia_destino_id: UUID | None = None
    enviar_acuse: bool = True


class AsociarRadicadoRequest(BaseModel):
    """POST /api/v1/gd/correo/{id}/asociar-radicado/{rad_id}."""
    observaciones: str | None = Field(default=None, max_length=2000)


class DescartarCorreoRequest(BaseModel):
    """POST /api/v1/gd/correo/{id}/descartar."""
    motivo: str = Field(min_length=10, max_length=2000)


class CorreoImportadoResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    buzon_id: UUID
    message_id: str
    remitente_email: str
    remitente_nombre: str | None = None
    destinatarios_to: list[str] = Field(default_factory=list)
    destinatarios_cc: list[str] = Field(default_factory=list)
    destinatarios_bcc: list[str] = Field(default_factory=list)
    asunto: str | None = None
    cuerpo_texto: str | None = None
    cuerpo_html: str | None = None
    fecha_envio_original: datetime | None = None
    importado_en: datetime
    anexos_archivo_ids: list[UUID] = Field(default_factory=list)
    estado: EstadoCorreoImportado
    radicado_id: UUID | None = None
    convertido_por_user_id: UUID | None = None
    fecha_decision: datetime | None = None
    motivo_descarte: str | None = None
    observaciones: str | None = None
    acuse_enviado_en: datetime | None = None
    acuse_estado: str | None = None


class CorreoImportadoListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[CorreoImportadoResponse]
    total: int


# =============================================================================
# Worker — resultado de ejecución
# =============================================================================

class WorkerExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    buzon_id: UUID
    correos_descargados: int
    correos_nuevos: int
    correos_duplicados_omitidos: int
    errores: int
    ultimo_message_id: str | None = None
    duracion_ms: int


class TestConexionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    buzon_id: UUID
    exitoso: bool
    mensaje: str
    detalles: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    # Enums
    'ProveedorCorreo', 'EstadoBuzon', 'EstadoCorreoImportado',
    # Requests
    'CrearBuzonRequest', 'PatchBuzonRequest',
    'ProbarConexionRequest', 'EjecutarWorkerRequest',
    'ConvertirCorreoRadicadoRequest', 'AsociarRadicadoRequest',
    'DescartarCorreoRequest',
    # Responses
    'BuzonResponse', 'BuzonListResponse',
    'CorreoImportadoResponse', 'CorreoImportadoListResponse',
    'WorkerExecutionResult', 'TestConexionResult',
]
