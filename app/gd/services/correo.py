"""Services para EP-012 correo institucional (bloque 13).

Cubre:
- CRUD buzón institucional (IMAP/Graph/Gmail/POP3)
- Worker de lectura periódica (idempotente vía message_id)
- Conversión correo → radicado (siempre humano, RNF-028)
- Asociar correo a radicado existente / descartar con motivo
- Provider stub IMailProvider (similar a IFirmaDigitalProvider, D31)
- Acuse de recibido configurable por buzón (GD-API-0076)
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Provider stub (GD-API-0073, 0074)
# =============================================================================

@dataclass
class CorreoCrudo:
    """Representación canónica de un correo descargado del proveedor."""
    message_id: str
    remitente_email: str
    remitente_nombre: str | None = None
    destinatarios_to: list[str] = field(default_factory=list)
    destinatarios_cc: list[str] = field(default_factory=list)
    destinatarios_bcc: list[str] = field(default_factory=list)
    asunto: str | None = None
    cuerpo_texto: str | None = None
    cuerpo_html: str | None = None
    fecha_envio_original: datetime | None = None
    anexos_archivo_ids: list[UUID] = field(default_factory=list)


class IMailProvider(ABC):
    """Interface para proveedores de correo (IMAP/Graph/Gmail).

    Stub permite tests deterministas; implementaciones reales se conectan
    via aiosmtplib/aiohttp respectivamente.
    """

    @abstractmethod
    async def test_conexion(
        self, *, host: str | None, port: int | None, usar_tls: bool,
        usuario: str | None, secret_vault_ref: str, config: dict[str, Any],
    ) -> dict[str, Any]:
        """Retorna {exitoso: bool, mensaje: str, detalles: dict}."""
        ...

    @abstractmethod
    async def descargar_correos(
        self, *, host: str | None, port: int | None, usar_tls: bool,
        usuario: str | None, secret_vault_ref: str, config: dict[str, Any],
        desde_message_id: str | None, max_correos: int,
    ) -> list[CorreoCrudo]:
        """Descarga correos del buzón ordenados por fecha. Idempotencia
        depende de message_id retornado."""
        ...

    @abstractmethod
    async def enviar_acuse(
        self, *, host: str | None, port: int | None, usar_tls: bool,
        usuario: str | None, secret_vault_ref: str, config: dict[str, Any],
        destinatario: str, asunto: str, cuerpo_texto: str,
    ) -> dict[str, Any]:
        """Envía acuse de recibido. Retorna {exitoso, mensaje}."""
        ...


class StubMailProvider(IMailProvider):
    """Stub determinista para tests/dev.

    No realiza conexión de red; genera correos sintéticos en `descargar_correos`
    si `config['seed_correos']` está presente.
    """

    async def test_conexion(self, **kwargs) -> dict[str, Any]:
        secret = kwargs.get('secret_vault_ref', '')
        if secret == 'invalid':
            return {'exitoso': False, 'mensaje': 'secret_vault_ref inválido',
                     'detalles': {}}
        return {'exitoso': True, 'mensaje': 'Conexión OK (stub)',
                 'detalles': {'proveedor': 'stub'}}

    async def descargar_correos(self, **kwargs) -> list[CorreoCrudo]:
        config = kwargs.get('config', {})
        max_correos = kwargs.get('max_correos', 50)
        seed = config.get('seed_correos', [])
        out = []
        for i, s in enumerate(seed[:max_correos]):
            out.append(CorreoCrudo(
                message_id=s.get('message_id', f'stub-{i}'),
                remitente_email=s.get('remitente_email', f'r{i}@example.com'),
                remitente_nombre=s.get('remitente_nombre'),
                destinatarios_to=s.get('destinatarios_to', []),
                asunto=s.get('asunto'),
                cuerpo_texto=s.get('cuerpo_texto'),
                cuerpo_html=s.get('cuerpo_html'),
                fecha_envio_original=s.get('fecha_envio_original'),
            ))
        return out

    async def enviar_acuse(self, **kwargs) -> dict[str, Any]:
        if kwargs.get('secret_vault_ref') == 'invalid':
            return {'exitoso': False, 'mensaje': 'credenciales inválidas'}
        return {'exitoso': True, 'mensaje': 'enviado (stub)'}


_default_provider: IMailProvider = StubMailProvider()


def get_default_provider() -> IMailProvider:
    return _default_provider


# =============================================================================
# CRUD buzón (GD-API-0073)
# =============================================================================

async def crear_buzon(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    nombre: str,
    direccion_correo: str,
    proveedor: str,
    dependencia_id: UUID | None,
    host: str | None,
    port: int | None,
    usar_tls: bool,
    usuario_smtp: str | None,
    config: dict[str, Any],
    secret_vault_ref: str,
    envio_acuse_recibido: bool,
    plantilla_acuse_id: UUID | None,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.buzon_correo_institucional (
                tenant_id, nombre, direccion_correo, proveedor,
                dependencia_id, host, port, usar_tls, usuario_smtp,
                config, secret_vault_ref, envio_acuse_recibido,
                plantilla_acuse_id, created_by_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
                    $11, $12, $13, $14)
            returning id, nombre, direccion_correo, proveedor, dependencia_id,
                      host, port, usar_tls, usuario_smtp, config,
                      secret_vault_ref, ultima_lectura_en,
                      envio_acuse_recibido, plantilla_acuse_id,
                      estado, ultimo_error_texto, ultimo_error_en,
                      created_at, updated_at
            """,
            tenant_id, nombre, direccion_correo, proveedor, dependencia_id,
            host, port, usar_tls, usuario_smtp, json.dumps(config),
            secret_vault_ref, envio_acuse_recibido, plantilla_acuse_id,
            created_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('direccion_correo_ya_registrada') from e
    d = dict(row)
    if isinstance(d['config'], str):
        d['config'] = json.loads(d['config'])
    return d


async def obtener_buzon(
    conn: asyncpg.Connection, *, tenant_id: UUID, buzon_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, nombre, direccion_correo, proveedor, dependencia_id,
               host, port, usar_tls, usuario_smtp, config, secret_vault_ref,
               ultima_lectura_en, envio_acuse_recibido, plantilla_acuse_id,
               estado, ultimo_error_texto, ultimo_error_en,
               created_at, updated_at
        from gd.buzon_correo_institucional
        where id = $1 and tenant_id = $2
        """,
        buzon_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d['config'], str):
        d['config'] = json.loads(d['config'])
    return d


async def listar_buzones(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: str | None = None,
    dependencia_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'dependencia_id = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, nombre, direccion_correo, proveedor, dependencia_id,
               host, port, usar_tls, usuario_smtp, config, secret_vault_ref,
               ultima_lectura_en, envio_acuse_recibido, plantilla_acuse_id,
               estado, ultimo_error_texto, ultimo_error_en,
               created_at, updated_at
        from gd.buzon_correo_institucional
        where {' and '.join(where)}
        order by nombre
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d['config'], str):
            d['config'] = json.loads(d['config'])
        out.append(d)
    return out


async def patch_buzon(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    buzon_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    exists = await conn.fetchval(
        'select 1 from gd.buzon_correo_institucional where id = $1 and tenant_id = $2',
        buzon_id, tenant_id,
    )
    if not exists:
        return None
    if not cambios:
        return await obtener_buzon(conn, tenant_id=tenant_id, buzon_id=buzon_id)

    sets, params = [], [buzon_id, tenant_id]
    for k, v in cambios.items():
        if k == 'config':
            params.append(json.dumps(v))
            sets.append(f'config = ${len(params)}::jsonb')
        else:
            params.append(v)
            sets.append(f'{k} = ${len(params)}')

    await conn.execute(
        f"""
        update gd.buzon_correo_institucional
        set {', '.join(sets)}
        where id = $1 and tenant_id = $2
        """,
        *params,
    )
    return await obtener_buzon(conn, tenant_id=tenant_id, buzon_id=buzon_id)


async def probar_conexion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    buzon_id: UUID,
    provider: IMailProvider | None = None,
) -> dict[str, Any] | None:
    bz = await obtener_buzon(conn, tenant_id=tenant_id, buzon_id=buzon_id)
    if bz is None:
        return None
    pv = provider or get_default_provider()
    result = await pv.test_conexion(
        host=bz['host'], port=bz['port'], usar_tls=bz['usar_tls'],
        usuario=bz['usuario_smtp'], secret_vault_ref=bz['secret_vault_ref'],
        config=bz['config'],
    )
    nuevo_estado = 'activa' if result['exitoso'] else 'error_credenciales'
    if nuevo_estado != bz['estado']:
        await conn.execute(
            """
            update gd.buzon_correo_institucional
            set estado = $3,
                ultimo_error_texto = case when $3 = 'error_credenciales' then $4
                                          else null end,
                ultimo_error_en = case when $3 = 'error_credenciales' then now()
                                       else ultimo_error_en end
            where id = $1 and tenant_id = $2
            """,
            buzon_id, tenant_id, nuevo_estado,
            result['mensaje'] if not result['exitoso'] else None,
        )
    return {'buzon_id': buzon_id, **result}


# =============================================================================
# Worker de lectura periódica (GD-API-0074)
# =============================================================================

async def ejecutar_worker(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    buzon_id: UUID,
    max_correos: int = 50,
    provider: IMailProvider | None = None,
) -> dict[str, Any] | None:
    """Descarga correos nuevos del buzón. Idempotente vía message_id.

    Retorna {buzon_id, correos_descargados, correos_nuevos,
    correos_duplicados_omitidos, errores, ultimo_message_id, duracion_ms}.
    """
    bz = await obtener_buzon(conn, tenant_id=tenant_id, buzon_id=buzon_id)
    if bz is None:
        return None
    if bz['estado'] != 'activa':
        raise ValueError(f"buzon_estado_invalido:{bz['estado']}")

    pv = provider or get_default_provider()
    t0 = time.monotonic()

    correos = await pv.descargar_correos(
        host=bz['host'], port=bz['port'], usar_tls=bz['usar_tls'],
        usuario=bz['usuario_smtp'], secret_vault_ref=bz['secret_vault_ref'],
        config=bz['config'],
        desde_message_id=None,  # podríamos pasar bz['ultimo_message_id_visto']
        max_correos=max_correos,
    )

    nuevos = 0
    duplicados = 0
    errores = 0
    ultimo_msg_id: str | None = None

    for c in correos:
        ultimo_msg_id = c.message_id
        try:
            await conn.fetchrow(
                """
                insert into gd.correo_importado (
                    tenant_id, buzon_id, message_id, remitente_email,
                    remitente_nombre, destinatarios_to, destinatarios_cc,
                    destinatarios_bcc, asunto, cuerpo_texto, cuerpo_html,
                    fecha_envio_original, anexos_archivo_ids
                )
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                returning id
                """,
                tenant_id, buzon_id, c.message_id, c.remitente_email,
                c.remitente_nombre,
                c.destinatarios_to, c.destinatarios_cc, c.destinatarios_bcc,
                c.asunto, c.cuerpo_texto, c.cuerpo_html,
                c.fecha_envio_original, c.anexos_archivo_ids,
            )
            nuevos += 1
        except asyncpg.UniqueViolationError:
            duplicados += 1
        except Exception:
            errores += 1

    # Update ultima_lectura_en + ultimo_message_id_visto.
    await conn.execute(
        """
        update gd.buzon_correo_institucional
        set ultima_lectura_en = now(),
            ultimo_message_id_visto = coalesce($3, ultimo_message_id_visto)
        where id = $1 and tenant_id = $2
        """,
        buzon_id, tenant_id, ultimo_msg_id,
    )

    return {
        'buzon_id': buzon_id,
        'correos_descargados': len(correos),
        'correos_nuevos': nuevos,
        'correos_duplicados_omitidos': duplicados,
        'errores': errores,
        'ultimo_message_id': ultimo_msg_id,
        'duracion_ms': int((time.monotonic() - t0) * 1000),
    }


# =============================================================================
# Correos importados — listar / detalle / decisiones (GD-API-0075)
# =============================================================================

async def obtener_correo(
    conn: asyncpg.Connection, *, tenant_id: UUID, correo_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, buzon_id, message_id, remitente_email, remitente_nombre,
               destinatarios_to, destinatarios_cc, destinatarios_bcc,
               asunto, cuerpo_texto, cuerpo_html, fecha_envio_original,
               importado_en, anexos_archivo_ids, estado, radicado_id,
               convertido_por_user_id, fecha_decision, motivo_descarte,
               observaciones, acuse_enviado_en, acuse_estado
        from gd.correo_importado
        where id = $1 and tenant_id = $2
        """,
        correo_id, tenant_id,
    )
    return dict(row) if row else None


async def listar_correos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    buzon_id: UUID | None = None,
    estado: str | None = None,
    remitente_email: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if buzon_id:
        params.append(buzon_id)
        where.append(f'buzon_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if remitente_email:
        params.append(remitente_email)
        where.append(f'remitente_email = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, buzon_id, message_id, remitente_email, remitente_nombre,
               destinatarios_to, destinatarios_cc, destinatarios_bcc,
               asunto, cuerpo_texto, cuerpo_html, fecha_envio_original,
               importado_en, anexos_archivo_ids, estado, radicado_id,
               convertido_por_user_id, fecha_decision, motivo_descarte,
               observaciones, acuse_enviado_en, acuse_estado
        from gd.correo_importado
        where {' and '.join(where)}
        order by importado_en desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_correos(
    conn: asyncpg.Connection, *, tenant_id: UUID, buzon_id: UUID | None = None,
) -> int:
    if buzon_id:
        n = await conn.fetchval(
            'select count(*) from gd.correo_importado '
            'where tenant_id = $1 and buzon_id = $2',
            tenant_id, buzon_id,
        )
    else:
        n = await conn.fetchval(
            'select count(*) from gd.correo_importado where tenant_id = $1',
            tenant_id,
        )
    return int(n or 0)


async def asociar_a_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correo_id: UUID,
    radicado_id: UUID,
    observaciones: str | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    c = await conn.fetchrow(
        'select estado from gd.correo_importado where id = $1 and tenant_id = $2',
        correo_id, tenant_id,
    )
    if c is None:
        return None
    if c['estado'] != 'pendiente':
        raise ValueError(f"estado_invalido:{c['estado']}")

    # Validar radicado existe.
    rad = await conn.fetchval(
        'select 1 from gd.radicado where id = $1 and tenant_id = $2',
        radicado_id, tenant_id,
    )
    if not rad:
        raise LookupError('radicado_no_existe')

    row = await conn.fetchrow(
        """
        update gd.correo_importado
        set estado = 'asociado_radicado',
            radicado_id = $3,
            convertido_por_user_id = $4,
            fecha_decision = now(),
            observaciones = $5
        where id = $1 and tenant_id = $2
        returning id, buzon_id, message_id, remitente_email, remitente_nombre,
                  destinatarios_to, destinatarios_cc, destinatarios_bcc,
                  asunto, cuerpo_texto, cuerpo_html, fecha_envio_original,
                  importado_en, anexos_archivo_ids, estado, radicado_id,
                  convertido_por_user_id, fecha_decision, motivo_descarte,
                  observaciones, acuse_enviado_en, acuse_estado
        """,
        correo_id, tenant_id, radicado_id, usuario_actor_id, observaciones,
    )
    return dict(row)


async def descartar_correo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correo_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    c = await conn.fetchrow(
        'select estado from gd.correo_importado where id = $1 and tenant_id = $2',
        correo_id, tenant_id,
    )
    if c is None:
        return None
    if c['estado'] != 'pendiente':
        raise ValueError(f"estado_invalido:{c['estado']}")

    row = await conn.fetchrow(
        """
        update gd.correo_importado
        set estado = 'descartado',
            motivo_descarte = $3,
            convertido_por_user_id = $4,
            fecha_decision = now()
        where id = $1 and tenant_id = $2
        returning id, buzon_id, message_id, remitente_email, remitente_nombre,
                  destinatarios_to, destinatarios_cc, destinatarios_bcc,
                  asunto, cuerpo_texto, cuerpo_html, fecha_envio_original,
                  importado_en, anexos_archivo_ids, estado, radicado_id,
                  convertido_por_user_id, fecha_decision, motivo_descarte,
                  observaciones, acuse_enviado_en, acuse_estado
        """,
        correo_id, tenant_id, motivo, usuario_actor_id,
    )
    return dict(row)


async def convertir_a_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correo_id: UUID,
    canal_id: UUID,
    asunto_override: str | None,
    descripcion: str | None,
    tercero_id: UUID | None,
    crear_tercero: bool,
    dependencia_destino_id: UUID | None,
    enviar_acuse: bool,
    usuario_actor_id: UUID,
    provider: IMailProvider | None = None,
) -> dict[str, Any] | None:
    """Convierte correo a radicado de entrada (humano-driven, RNF-028).

    Pasos:
    1. Validar correo en estado='pendiente'.
    2. Si crear_tercero=true → svc_terceros.crear_tercero con remitente.
    3. Crear radicado tipo='entrada' con asunto + descripción + tercero.
    4. Actualizar correo: estado='convertido_radicado', radicado_id=...
    5. Si enviar_acuse y buzón.envio_acuse_recibido → llamar provider.
    """
    from app.gd.services import radicados as svc_rad
    from app.gd.services import terceros as svc_ter

    c = await conn.fetchrow(
        """
        select c.estado, c.buzon_id, c.remitente_email, c.remitente_nombre,
               c.asunto, c.cuerpo_texto,
               b.envio_acuse_recibido, b.host, b.port, b.usar_tls,
               b.usuario_smtp, b.secret_vault_ref, b.config
        from gd.correo_importado c
        join gd.buzon_correo_institucional b on b.id = c.buzon_id
        where c.id = $1 and c.tenant_id = $2
        """,
        correo_id, tenant_id,
    )
    if c is None:
        return None
    if c['estado'] != 'pendiente':
        raise ValueError(f"estado_invalido:{c['estado']}")

    # Crear tercero si solicita.
    tercero_resuelto = tercero_id
    if crear_tercero and tercero_resuelto is None:
        nombres = c['remitente_nombre'] or c['remitente_email'].split('@')[0]
        try:
            t_row = await svc_ter.crear_tercero(
                conn, tenant_id=tenant_id,
                datos={
                    'tipo_tercero': 'persona_natural',
                    'tipo_documento': 'CC',
                    'numero_documento': f'EMAIL-{c["remitente_email"][:30]}',
                    'nombres': nombres,
                    'apellidos': '',
                    'email': c['remitente_email'],
                },
                created_by_user_id=usuario_actor_id,
            )
            tercero_resuelto = t_row['id']
        except Exception:
            # Si ya existe o falla, continuar con tercero=None.
            tercero_resuelto = None

    # Crear radicado de entrada.
    asunto_final = asunto_override or c['asunto'] or '(sin asunto)'
    desc_final = descripcion or (c['cuerpo_texto'][:2000] if c['cuerpo_texto'] else None)
    rad = await svc_rad.crear_radicado(
        conn, tenant_id=tenant_id,
        tipo_radicado='entrada', canal_id=canal_id,
        asunto=asunto_final, descripcion=desc_final,
        tercero_id=tercero_resuelto, tercero_destinatario_id=None,
        dependencia_origen_id=None,
        dependencia_destino_id=dependencia_destino_id,
        documento_principal_id=None,
        usuario_radicador_id=usuario_actor_id,
        actor_snapshot={'origen': 'correo_importado',
                         'correo_id': str(correo_id)},
        radicado_relacionado_id=None,
    )

    # Actualizar correo.
    await conn.execute(
        """
        update gd.correo_importado
        set estado = 'convertido_radicado',
            radicado_id = $3,
            convertido_por_user_id = $4,
            fecha_decision = now()
        where id = $1 and tenant_id = $2
        """,
        correo_id, tenant_id, rad['id'], usuario_actor_id,
    )

    # Enviar acuse si configurado.
    acuse_estado = 'no_aplica'
    if enviar_acuse and c['envio_acuse_recibido']:
        pv = provider or get_default_provider()
        try:
            ack = await pv.enviar_acuse(
                host=c['host'], port=c['port'], usar_tls=c['usar_tls'],
                usuario=c['usuario_smtp'],
                secret_vault_ref=c['secret_vault_ref'],
                config=c['config'] if isinstance(c['config'], dict) else json.loads(c['config']),
                destinatario=c['remitente_email'],
                asunto=f"Acuse de recibido: radicado {rad['numero_radicado']}",
                cuerpo_texto=(
                    f"Su comunicación fue radicada con número "
                    f"{rad['numero_radicado']}."
                ),
            )
            acuse_estado = 'enviado' if ack['exitoso'] else 'error'
            if not ack['exitoso']:
                await conn.execute(
                    """
                    update gd.correo_importado
                    set acuse_estado = 'error', acuse_error_texto = $3
                    where id = $1 and tenant_id = $2
                    """,
                    correo_id, tenant_id, ack['mensaje'],
                )
            else:
                await conn.execute(
                    """
                    update gd.correo_importado
                    set acuse_estado = 'enviado', acuse_enviado_en = now()
                    where id = $1 and tenant_id = $2
                    """,
                    correo_id, tenant_id,
                )
        except Exception as e:
            acuse_estado = 'error'
            await conn.execute(
                """
                update gd.correo_importado
                set acuse_estado = 'error', acuse_error_texto = $3
                where id = $1 and tenant_id = $2
                """,
                correo_id, tenant_id, str(e)[:500],
            )

    correo_actualizado = await obtener_correo(
        conn, tenant_id=tenant_id, correo_id=correo_id,
    )
    return {
        'correo': correo_actualizado,
        'radicado_id': rad['id'],
        'radicado_numero': rad['numero_radicado'],
        'acuse_estado': acuse_estado,
    }


__all__ = [
    # Provider
    'IMailProvider', 'StubMailProvider', 'get_default_provider',
    'CorreoCrudo',
    # Buzones
    'crear_buzon', 'obtener_buzon', 'listar_buzones', 'patch_buzon',
    'probar_conexion',
    # Worker
    'ejecutar_worker',
    # Correos
    'obtener_correo', 'listar_correos', 'contar_correos',
    'asociar_a_radicado', 'descartar_correo', 'convertir_a_radicado',
]
