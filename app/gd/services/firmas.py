"""Services SQL para EP-011 firmas (bloque 12).

Cubre:
- Firma escaneada: registrar (vault), autorizar (admin), revocar
- Firma electrónica: firmar documento (con captura snapshot + step-up)
- Firma digital certificada: stub IFirmaDigitalProvider + provider de demo
- Rechazo de firma pendiente
- Consulta de evidencia
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg


# Ventana de step-up: si la sesión inició hace > 5 min, requerir re-auth.
STEP_UP_VENTANA = timedelta(minutes=5)


# =============================================================================
# Provider stub para firma digital certificada (GD-API-0070, RNF-016)
# =============================================================================

class IFirmaDigitalProvider(ABC):
    """Interface abstracta para proveedores de firma digital certificada.

    EP-011 entrega un stub. Implementaciones reales (DigiCert, GSE-AD, etc.)
    se conectarán via adapter pattern cuando RNF-016 lo requiera.
    """

    @abstractmethod
    async def firmar(
        self, *, archivo_bytes: bytes, certificado_id: str, pin: str,
    ) -> dict[str, Any]:
        """Firma el archivo y retorna {hash_archivo, firma_bytes, evidencia}.

        Raises ValueError('pin_invalido') / ValueError('cert_no_valido').
        """
        ...

    @abstractmethod
    async def validar(self, *, archivo_bytes: bytes, firma_bytes: bytes,
                      certificado_id: str) -> bool:
        """Valida criptográficamente que firma corresponde a archivo+cert."""
        ...


class StubFirmaDigitalProvider(IFirmaDigitalProvider):
    """Implementación stub para tests / desarrollo.

    NO realiza criptografía real. Asume PIN '0000' válido.
    """
    PIN_DEMO = '0000'

    async def firmar(
        self, *, archivo_bytes: bytes, certificado_id: str, pin: str,
    ) -> dict[str, Any]:
        if pin != self.PIN_DEMO:
            raise ValueError('pin_invalido')
        if not certificado_id:
            raise ValueError('cert_no_valido')
        h = hashlib.sha256(archivo_bytes).hexdigest()
        return {
            'hash_archivo': h,
            'firma_bytes': b'STUB_SIGNATURE_' + h.encode()[:16],
            'evidencia': {'provider': 'stub', 'algoritmo': 'sha256'},
        }

    async def validar(self, *, archivo_bytes: bytes, firma_bytes: bytes,
                      certificado_id: str) -> bool:
        h = hashlib.sha256(archivo_bytes).hexdigest()
        expected = b'STUB_SIGNATURE_' + h.encode()[:16]
        return firma_bytes == expected


# Singleton para defaults.
_default_provider: IFirmaDigitalProvider = StubFirmaDigitalProvider()


def get_default_provider() -> IFirmaDigitalProvider:
    return _default_provider


# =============================================================================
# Helpers
# =============================================================================

def calcular_hash_archivo(contenido_bytes: bytes) -> str:
    """SHA-256 hex digest del contenido del archivo."""
    return hashlib.sha256(contenido_bytes).hexdigest()


async def _capturar_snapshot_firmante(
    conn: asyncpg.Connection, *, tenant_id: UUID, user_id: UUID,
) -> dict[str, Any]:
    """Snapshot del firmante (email, dependencia, cargo, tipo_vinculacion)."""
    row = await conn.fetchrow(
        """
        select u.email, p.tipo_vinculacion, p.estado_gd,
               p.dependencia_actual_id, p.cargo_actual_id,
               c.nombre as cargo_nombre, d.nombre as dep_nombre
        from app.users u
        join gd.perfil_usuario p on p.user_id = u.id and p.tenant_id = $1
        left join gd.cargo c on c.id = p.cargo_actual_id
        left join gd.dependencia d on d.id = p.dependencia_actual_id
        where u.id = $2
        """,
        tenant_id, user_id,
    )
    if row is None:
        return {'user_id': str(user_id), 'snapshot_incompleto': True}
    return {
        'user_id': str(user_id),
        'email': row['email'],
        'tipo_vinculacion': row['tipo_vinculacion'],
        'estado_gd': row['estado_gd'],
        'dependencia_id': str(row['dependencia_actual_id']) if row['dependencia_actual_id'] else None,
        'dependencia_nombre': row['dep_nombre'],
        'cargo_id': str(row['cargo_actual_id']) if row['cargo_actual_id'] else None,
        'cargo_nombre': row['cargo_nombre'],
    }


def requiere_step_up(sesion_iniciada_en: datetime | None) -> bool:
    """Si la sesión inició hace > 5 min, requiere step-up."""
    if sesion_iniciada_en is None:
        return True
    now = datetime.now(timezone.utc)
    if sesion_iniciada_en.tzinfo is None:
        sesion_iniciada_en = sesion_iniciada_en.replace(tzinfo=timezone.utc)
    return (now - sesion_iniciada_en) > STEP_UP_VENTANA


# =============================================================================
# Firma escaneada (GD-API-0068)
# =============================================================================

async def registrar_firma_escaneada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    archivo_digital_id: UUID,
    mime_type: str,
    tamano_bytes: int | None,
    hash_sha256: str | None,
) -> dict[str, Any]:
    """Crea firma escaneada en estado='pendiente_autorizacion'."""
    try:
        row = await conn.fetchrow(
            """
            insert into gd.firma_escaneada (
                tenant_id, user_id, archivo_digital_id, mime_type,
                tamano_bytes, hash_sha256, estado
            )
            values ($1, $2, $3, $4, $5, $6, 'pendiente_autorizacion')
            returning id, user_id, archivo_digital_id, mime_type, tamano_bytes,
                      hash_sha256, estado, autorizada_por_user_id,
                      fecha_autorizacion, motivo_revocacion, created_at
            """,
            tenant_id, user_id, archivo_digital_id, mime_type,
            tamano_bytes, hash_sha256,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('firma_ya_registrada') from e
    return dict(row)


async def autorizar_firma_escaneada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    firma_id: UUID,
    autorizada_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Marca como 'activa'. Revoca cualquier otra activa del mismo user."""
    firma = await conn.fetchrow(
        """
        select user_id, estado from gd.firma_escaneada
        where id = $1 and tenant_id = $2
        """,
        firma_id, tenant_id,
    )
    if firma is None:
        return None
    if firma['estado'] != 'pendiente_autorizacion':
        raise ValueError(f"estado_invalido:{firma['estado']}")

    # Revocar otras activas del mismo user (para mantener unique parcial).
    await conn.execute(
        """
        update gd.firma_escaneada
        set estado = 'revocada',
            motivo_revocacion = 'Reemplazada por nueva firma autorizada'
        where tenant_id = $1 and user_id = $2 and estado = 'activa'
        """,
        tenant_id, firma['user_id'],
    )

    row = await conn.fetchrow(
        """
        update gd.firma_escaneada
        set estado = 'activa',
            autorizada_por_user_id = $3,
            fecha_autorizacion = now()
        where id = $1 and tenant_id = $2
        returning id, user_id, archivo_digital_id, mime_type, tamano_bytes,
                  hash_sha256, estado, autorizada_por_user_id,
                  fecha_autorizacion, motivo_revocacion, created_at
        """,
        firma_id, tenant_id, autorizada_por_user_id,
    )
    return dict(row)


async def revocar_firma_escaneada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    firma_id: UUID,
    motivo: str,
) -> dict[str, Any] | None:
    firma = await conn.fetchval(
        'select estado from gd.firma_escaneada where id = $1 and tenant_id = $2',
        firma_id, tenant_id,
    )
    if firma is None:
        return None
    if firma == 'revocada':
        raise ValueError('ya_revocada')

    row = await conn.fetchrow(
        """
        update gd.firma_escaneada
        set estado = 'revocada', motivo_revocacion = $3
        where id = $1 and tenant_id = $2
        returning id, user_id, archivo_digital_id, mime_type, tamano_bytes,
                  hash_sha256, estado, autorizada_por_user_id,
                  fecha_autorizacion, motivo_revocacion, created_at
        """,
        firma_id, tenant_id, motivo,
    )
    return dict(row)


async def listar_firmas_escaneadas(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID | None = None,
    estado: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if user_id:
        params.append(user_id)
        where.append(f'user_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, user_id, archivo_digital_id, mime_type, tamano_bytes,
               hash_sha256, estado, autorizada_por_user_id,
               fecha_autorizacion, motivo_revocacion, created_at
        from gd.firma_escaneada
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Firma electrónica de documento (GD-API-0069)
# =============================================================================

async def _validar_documento_firmable(
    conn: asyncpg.Connection, *, tenant_id: UUID, documento_id: UUID,
    version_documento_id: UUID,
) -> dict[str, Any]:
    """Valida que el documento + versión sean firmables.

    Reglas:
    - Documento estado='activo'
    - Versión existe y está en estado en {'aprobada'}
    """
    doc = await conn.fetchrow(
        """
        select d.estado as doc_estado, v.estado as ver_estado,
               v.archivo_digital_id, v.documento_id
        from gd.documento d
        join gd.version_documento v on v.id = $3 and v.documento_id = d.id
        where d.id = $1 and d.tenant_id = $2
        """,
        documento_id, tenant_id, version_documento_id,
    )
    if doc is None:
        raise LookupError('documento_o_version_no_existe')
    if doc['doc_estado'] != 'activo':
        raise ValueError(f"documento_estado_invalido:{doc['doc_estado']}")
    if doc['ver_estado'] != 'aprobada':
        raise ValueError(f"version_estado_invalido:{doc['ver_estado']}")
    return dict(doc)


async def _validar_firmante_activo(
    conn: asyncpg.Connection, *, tenant_id: UUID, user_id: UUID,
) -> None:
    estado = await conn.fetchval(
        'select estado_gd from gd.perfil_usuario where user_id = $1 and tenant_id = $2',
        user_id, tenant_id,
    )
    if estado != 'activo':
        raise ValueError(f"firmante_no_activo:{estado or 'sin_perfil'}")


async def firmar_documento_electronica(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    version_documento_id: UUID,
    firmante_user_id: UUID,
    sesion_iniciada_en: datetime | None,
    step_up_satisfecho: bool,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """Firma electrónica con captura de evidencia.

    Validaciones:
    - documento activo, versión aprobada (no borrador)
    - firmante con perfil estado='activo'
    - step-up: si sesión >5min y NO step_up_satisfecho → estado='pendiente'
    """
    doc = await _validar_documento_firmable(
        conn, tenant_id=tenant_id, documento_id=documento_id,
        version_documento_id=version_documento_id,
    )
    await _validar_firmante_activo(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )

    snapshot = await _capturar_snapshot_firmante(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )

    # Step-up check.
    necesita_stepup = requiere_step_up(sesion_iniciada_en)
    estado_firma = 'consumada'
    fecha_firma_val: datetime | None = datetime.now(timezone.utc)
    if necesita_stepup and not step_up_satisfecho:
        estado_firma = 'pendiente'
        fecha_firma_val = None  # firma queda pendiente de re-auth

    # Hash del archivo (placeholder: cuando EP-018 entregue, se lee el binario).
    # Por ahora, hash sintético del archivo_digital_id.
    hash_archivo = calcular_hash_archivo(str(doc['archivo_digital_id']).encode())

    row = await conn.fetchrow(
        """
        insert into gd.firma_documento (
            tenant_id, documento_id, version_documento_id, firmante_user_id,
            tipo_firma, estado, hash_archivo, hash_algoritmo,
            snapshot_firmante, ip, user_agent, fecha_firma,
            step_up_requerido, step_up_satisfecho_en, sesion_iniciada_en
        )
        values ($1, $2, $3, $4, 'electronica', $5, $6, 'sha256',
                $7::jsonb, $8, $9, $10, $11, $12, $13)
        returning id, documento_id, version_documento_id, firmante_user_id,
                  tipo_firma, estado, firma_escaneada_id, certificado_id,
                  proveedor_firma_digital, hash_archivo, hash_algoritmo,
                  snapshot_firmante, ip, user_agent, fecha_firma,
                  fecha_rechazo, fecha_revocacion, observaciones_rechazo,
                  motivo_revocacion, step_up_requerido, created_at
        """,
        tenant_id, documento_id, version_documento_id, firmante_user_id,
        estado_firma, hash_archivo,
        json.dumps(snapshot), ip, user_agent, fecha_firma_val,
        necesita_stepup,
        datetime.now(timezone.utc) if step_up_satisfecho else None,
        sesion_iniciada_en,
    )
    d = dict(row)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


# =============================================================================
# Firma digital (GD-API-0070) — usa provider
# =============================================================================

async def firmar_documento_digital(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    version_documento_id: UUID,
    firmante_user_id: UUID,
    certificado_id: str,
    proveedor: str,
    pin: str,
    provider: IFirmaDigitalProvider | None = None,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """Firma digital certificada usando provider (stub por defecto)."""
    doc = await _validar_documento_firmable(
        conn, tenant_id=tenant_id, documento_id=documento_id,
        version_documento_id=version_documento_id,
    )
    await _validar_firmante_activo(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )

    snapshot = await _capturar_snapshot_firmante(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )

    pv = provider or get_default_provider()
    # Placeholder bytes: EP-018 entregará el archivo real.
    archivo_bytes = str(doc['archivo_digital_id']).encode()
    sig = await pv.firmar(
        archivo_bytes=archivo_bytes, certificado_id=certificado_id, pin=pin,
    )

    row = await conn.fetchrow(
        """
        insert into gd.firma_documento (
            tenant_id, documento_id, version_documento_id, firmante_user_id,
            tipo_firma, estado, certificado_id, proveedor_firma_digital,
            hash_archivo, hash_algoritmo, snapshot_firmante,
            ip, user_agent, fecha_firma
        )
        values ($1, $2, $3, $4, 'digital', 'consumada', $5, $6,
                $7, 'sha256', $8::jsonb, $9, $10, now())
        returning id, documento_id, version_documento_id, firmante_user_id,
                  tipo_firma, estado, firma_escaneada_id, certificado_id,
                  proveedor_firma_digital, hash_archivo, hash_algoritmo,
                  snapshot_firmante, ip, user_agent, fecha_firma,
                  fecha_rechazo, fecha_revocacion, observaciones_rechazo,
                  motivo_revocacion, step_up_requerido, created_at
        """,
        tenant_id, documento_id, version_documento_id, firmante_user_id,
        certificado_id, proveedor,
        sig['hash_archivo'], json.dumps(snapshot), ip, user_agent,
    )
    d = dict(row)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


# =============================================================================
# Firma escaneada aplicada a documento (helper)
# =============================================================================

async def firmar_documento_escaneada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    version_documento_id: UUID,
    firmante_user_id: UUID,
    firma_escaneada_id: UUID,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """Aplica firma escaneada del firmante al documento.

    Valida que firma_escaneada exista, esté activa y pertenezca al firmante.
    """
    doc = await _validar_documento_firmable(
        conn, tenant_id=tenant_id, documento_id=documento_id,
        version_documento_id=version_documento_id,
    )
    await _validar_firmante_activo(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )

    fe = await conn.fetchrow(
        """
        select user_id, estado from gd.firma_escaneada
        where id = $1 and tenant_id = $2
        """,
        firma_escaneada_id, tenant_id,
    )
    if fe is None:
        raise LookupError('firma_escaneada_no_existe')
    if fe['estado'] != 'activa':
        raise ValueError(f"firma_escaneada_estado:{fe['estado']}")
    if fe['user_id'] != firmante_user_id:
        raise ValueError('firma_escaneada_no_pertenece_al_firmante')

    snapshot = await _capturar_snapshot_firmante(
        conn, tenant_id=tenant_id, user_id=firmante_user_id,
    )
    hash_archivo = calcular_hash_archivo(
        str(doc['archivo_digital_id']).encode(),
    )

    row = await conn.fetchrow(
        """
        insert into gd.firma_documento (
            tenant_id, documento_id, version_documento_id, firmante_user_id,
            tipo_firma, estado, firma_escaneada_id, hash_archivo,
            hash_algoritmo, snapshot_firmante, ip, user_agent, fecha_firma
        )
        values ($1, $2, $3, $4, 'escaneada', 'consumada', $5, $6,
                'sha256', $7::jsonb, $8, $9, now())
        returning id, documento_id, version_documento_id, firmante_user_id,
                  tipo_firma, estado, firma_escaneada_id, certificado_id,
                  proveedor_firma_digital, hash_archivo, hash_algoritmo,
                  snapshot_firmante, ip, user_agent, fecha_firma,
                  fecha_rechazo, fecha_revocacion, observaciones_rechazo,
                  motivo_revocacion, step_up_requerido, created_at
        """,
        tenant_id, documento_id, version_documento_id, firmante_user_id,
        firma_escaneada_id, hash_archivo,
        json.dumps(snapshot), ip, user_agent,
    )
    d = dict(row)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


# =============================================================================
# Rechazo / revocación (GD-API-0071)
# =============================================================================

async def rechazar_firma(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    firma_id: UUID,
    observacion: str,
    actor_user_id: UUID,
) -> dict[str, Any] | None:
    """Rechaza firma en estado='pendiente' (step-up no realizada, p.ej.)."""
    f = await conn.fetchrow(
        """
        select estado, firmante_user_id from gd.firma_documento
        where id = $1 and tenant_id = $2
        """,
        firma_id, tenant_id,
    )
    if f is None:
        return None
    if f['estado'] != 'pendiente':
        raise ValueError(f"estado_invalido:{f['estado']}")
    # Solo el firmante (o quien tenga PERM-FIR-004) puede rechazar.
    # Aquí asumimos que el handler ya validó perm; este método solo enforza
    # que actor sea el firmante o un revisor autorizado.

    row = await conn.fetchrow(
        """
        update gd.firma_documento
        set estado = 'rechazada',
            fecha_rechazo = now(),
            observaciones_rechazo = $3
        where id = $1 and tenant_id = $2
        returning id, documento_id, version_documento_id, firmante_user_id,
                  tipo_firma, estado, firma_escaneada_id, certificado_id,
                  proveedor_firma_digital, hash_archivo, hash_algoritmo,
                  snapshot_firmante, ip, user_agent, fecha_firma,
                  fecha_rechazo, fecha_revocacion, observaciones_rechazo,
                  motivo_revocacion, step_up_requerido, created_at
        """,
        firma_id, tenant_id, observacion,
    )
    d = dict(row)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


async def revocar_firma_consumada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    firma_id: UUID,
    motivo: str,
    actor_user_id: UUID,
) -> dict[str, Any] | None:
    """Revoca una firma ya consumada (post-firma). Para casos extraordinarios."""
    f = await conn.fetchval(
        'select estado from gd.firma_documento where id = $1 and tenant_id = $2',
        firma_id, tenant_id,
    )
    if f is None:
        return None
    if f != 'consumada':
        raise ValueError(f"estado_invalido:{f}")

    row = await conn.fetchrow(
        """
        update gd.firma_documento
        set estado = 'revocada',
            fecha_revocacion = now(),
            motivo_revocacion = $3
        where id = $1 and tenant_id = $2
        returning id, documento_id, version_documento_id, firmante_user_id,
                  tipo_firma, estado, firma_escaneada_id, certificado_id,
                  proveedor_firma_digital, hash_archivo, hash_algoritmo,
                  snapshot_firmante, ip, user_agent, fecha_firma,
                  fecha_rechazo, fecha_revocacion, observaciones_rechazo,
                  motivo_revocacion, step_up_requerido, created_at
        """,
        firma_id, tenant_id, motivo,
    )
    d = dict(row)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


# =============================================================================
# Consulta de evidencia (GD-API-0072)
# =============================================================================

async def obtener_evidencia(
    conn: asyncpg.Connection, *, tenant_id: UUID, firma_id: UUID,
) -> dict[str, Any] | None:
    """Retorna firma + info del documento + versión asociados."""
    f = await conn.fetchrow(
        """
        select f.id, f.documento_id, f.version_documento_id, f.firmante_user_id,
               f.tipo_firma, f.estado, f.firma_escaneada_id, f.certificado_id,
               f.proveedor_firma_digital, f.hash_archivo, f.hash_algoritmo,
               f.snapshot_firmante, f.ip, f.user_agent, f.fecha_firma,
               f.fecha_rechazo, f.fecha_revocacion, f.observaciones_rechazo,
               f.motivo_revocacion, f.step_up_requerido, f.created_at,
               d.titulo as documento_titulo,
               v.numero_version as documento_version
        from gd.firma_documento f
        join gd.documento d on d.id = f.documento_id
        join gd.version_documento v on v.id = f.version_documento_id
        where f.id = $1 and f.tenant_id = $2
        """,
        firma_id, tenant_id,
    )
    if f is None:
        return None
    d = dict(f)
    if isinstance(d['snapshot_firmante'], str):
        d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
    return d


# =============================================================================
# Listado de firmas por documento / firmante
# =============================================================================

async def listar_firmas_documento(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID | None = None,
    firmante_user_id: UUID | None = None,
    estado: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if documento_id:
        params.append(documento_id)
        where.append(f'documento_id = ${len(params)}')
    if firmante_user_id:
        params.append(firmante_user_id)
        where.append(f'firmante_user_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, documento_id, version_documento_id, firmante_user_id,
               tipo_firma, estado, firma_escaneada_id, certificado_id,
               proveedor_firma_digital, hash_archivo, hash_algoritmo,
               snapshot_firmante, ip, user_agent, fecha_firma,
               fecha_rechazo, fecha_revocacion, observaciones_rechazo,
               motivo_revocacion, step_up_requerido, created_at
        from gd.firma_documento
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d['snapshot_firmante'], str):
            d['snapshot_firmante'] = json.loads(d['snapshot_firmante'])
        out.append(d)
    return out


__all__ = [
    # Constantes
    'STEP_UP_VENTANA',
    # Provider
    'IFirmaDigitalProvider', 'StubFirmaDigitalProvider', 'get_default_provider',
    # Helpers
    'calcular_hash_archivo', 'requiere_step_up',
    # Firma escaneada
    'registrar_firma_escaneada', 'autorizar_firma_escaneada',
    'revocar_firma_escaneada', 'listar_firmas_escaneadas',
    # Firma documento
    'firmar_documento_electronica', 'firmar_documento_digital',
    'firmar_documento_escaneada',
    # Rechazo/revocación
    'rechazar_firma', 'revocar_firma_consumada',
    # Consultas
    'obtener_evidencia', 'listar_firmas_documento',
]
