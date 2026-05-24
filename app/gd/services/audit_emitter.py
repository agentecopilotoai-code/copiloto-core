"""GD-API-0117 — Helper Python para emitir eventos a `core.evento_auditoria`.

Wrapper sobre la función SQL `core.emit_evento_auditoria` (definida en
infra/postgres/04-gd-schema.sql sección 1.3). Provee API tipada y validación
de criticidad/dominio antes de tocar DB.

Convive con `app/services/audit.py` existente — ese sigue siendo el helper
oficial para eventos del producto principal (escribe a `app.audit_logs`).
Este helper es para eventos del módulo GD (escribe a `core.evento_auditoria`
con `dominio='gd'`).

Patrón de uso típico desde un handler::

    from app.gd.services.audit_emitter import emit_gd_event, AuditCriticidad

    await emit_gd_event(
        conn=conn,
        tipo_evento='gd.perfil_usuario.creado',
        accion='crear',
        tenant_id=tenant_id,
        usuario_id=request.state.user_id,
        actor_snapshot=snapshot,
        entidad_afectada_tipo='perfil_usuario',
        entidad_afectada_id=perfil_id,
        valor_nuevo={'tipo_vinculacion': 'planta', ...},
        criticidad=AuditCriticidad.MEDIA,
        request_id=request.state.request_id,
    )
"""
from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

import asyncpg


class AuditCriticidad(str, enum.Enum):
    """Niveles de criticidad permitidos en `core.evento_auditoria.criticidad`.

    Espejo del CHECK definido en SQL — mantener sincronizado con
    infra/postgres/04-gd-schema.sql.
    """

    BAJA = 'baja'
    MEDIA = 'media'
    ALTA = 'alta'
    CRITICA = 'critica'


class AuditDominio(str, enum.Enum):
    """Origen del evento — mantener sincronizado con el CHECK en SQL."""

    CORE = 'core'
    APP = 'app'
    GD = 'gd'
    KNOWLEDGE = 'knowledge'


_VALID_CRITICIDAD = {c.value for c in AuditCriticidad}
_VALID_DOMINIO = {d.value for d in AuditDominio}


async def emit_audit_event(  # noqa: PLR0913 — auditoría exige todos los campos
    conn: asyncpg.Connection,
    *,
    dominio: str,
    tipo_evento: str,
    accion: str,
    tenant_id: UUID | None = None,
    usuario_id: UUID | None = None,
    actor_snapshot: dict[str, Any] | None = None,
    entidad_afectada_tipo: str | None = None,
    entidad_afectada_id: UUID | None = None,
    entidad_afectada_identificador: str | None = None,
    valor_anterior: dict[str, Any] | None = None,
    valor_nuevo: dict[str, Any] | None = None,
    justificacion: str | None = None,
    detalles: dict[str, Any] | None = None,
    criticidad: AuditCriticidad | str = AuditCriticidad.MEDIA,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> UUID:
    """Inserta un evento en `core.evento_auditoria` y retorna su id.

    Convención GD-API-0117: usar este helper en lugar de INSERT manual para
    garantizar que todos los campos snapshot quedan registrados de forma
    consistente.

    Args:
        conn: conexión asyncpg con tenant_id ya seteado vía `app.db.pool.get_db`.
        dominio: uno de 'core'|'app'|'gd'|'knowledge'.
        tipo_evento: identificador semántico del evento (ej. 'gd.radicado.creado').
        accion: verbo de la operación (ej. 'crear', 'actualizar', 'anular').
        criticidad: nivel de severidad.
        tenant_id: requerido salvo eventos globales (de tipo core/app sin scope).
        usuario_id: UUID del actor humano si aplica.
        actor_snapshot: dict inmutable con datos del actor al momento del evento.
            Estructura sugerida: {'nombre_completo', 'rol_codigo', 'rol_nombre',
            'dependencia_codigo', 'dependencia_nombre', 'cargo', 'capturado_en'}.
        entidad_afectada_*: el recurso sobre el que se actuó.
        valor_anterior / valor_nuevo: estado del recurso antes y después.
        justificacion: motivo textual obligatorio en operaciones críticas.
        detalles: jsonb libre con metadata adicional.
        request_id / ip / user_agent: contexto de la HTTP request.

    Returns:
        UUID del evento recién insertado.

    Raises:
        ValueError: si dominio o criticidad están fuera del enum permitido.
        asyncpg.PostgresError: si el INSERT falla (RLS, FK rota, etc.).
    """
    criticidad_value = criticidad.value if isinstance(criticidad, AuditCriticidad) else criticidad
    if criticidad_value not in _VALID_CRITICIDAD:
        raise ValueError(
            f"criticidad inválida: {criticidad_value!r}. "
            f"Permitidas: {sorted(_VALID_CRITICIDAD)}."
        )
    if dominio not in _VALID_DOMINIO:
        raise ValueError(
            f"dominio inválido: {dominio!r}. Permitidos: {sorted(_VALID_DOMINIO)}."
        )

    row = await conn.fetchrow(
        """
        select core.emit_evento_auditoria(
            p_dominio                          := $1,
            p_tipo_evento                      := $2,
            p_accion                           := $3,
            p_tenant_id                        := $4,
            p_usuario_id                       := $5,
            p_actor_snapshot                   := $6::jsonb,
            p_entidad_afectada_tipo            := $7,
            p_entidad_afectada_id              := $8,
            p_entidad_afectada_identificador   := $9,
            p_valor_anterior                   := $10::jsonb,
            p_valor_nuevo                      := $11::jsonb,
            p_justificacion                    := $12,
            p_detalles                         := $13::jsonb,
            p_criticidad                       := $14,
            p_request_id                       := $15,
            p_ip                               := $16::inet,
            p_user_agent                       := $17
        ) as id
        """,
        dominio,
        tipo_evento,
        accion,
        tenant_id,
        usuario_id,
        _jsonb(actor_snapshot or {}),
        entidad_afectada_tipo,
        entidad_afectada_id,
        entidad_afectada_identificador,
        _jsonb(valor_anterior) if valor_anterior is not None else None,
        _jsonb(valor_nuevo) if valor_nuevo is not None else None,
        justificacion,
        _jsonb(detalles or {}),
        criticidad_value,
        request_id,
        ip,
        user_agent,
    )
    return row['id']  # type: ignore[no-any-return]


async def emit_gd_event(
    conn: asyncpg.Connection,
    *,
    tipo_evento: str,
    accion: str,
    tenant_id: UUID,
    **kwargs: Any,
) -> UUID:
    """Atajo para eventos con `dominio='gd'` (el caso 99% común en este módulo).

    Equivalente a llamar `emit_audit_event` con `dominio='gd'`.
    """
    return await emit_audit_event(
        conn,
        dominio=AuditDominio.GD.value,
        tipo_evento=tipo_evento,
        accion=accion,
        tenant_id=tenant_id,
        **kwargs,
    )


def _jsonb(value: dict[str, Any] | list[Any]) -> str:
    """Serializa a JSON para parámetros `$N::jsonb` en asyncpg.

    asyncpg acepta dict/list directamente para columnas jsonb cuando se hace
    cast explícito ($N::jsonb), pero algunos drivers requieren str. Usar
    json.dumps explícito evita ambigüedad y permite tipar el retorno.
    """
    import json
    return json.dumps(value, default=str)


__all__ = [
    'AuditCriticidad',
    'AuditDominio',
    'emit_audit_event',
    'emit_gd_event',
]
