"""Services SQL para EP-009 documentos, anexos, versiones (bloque 10).

Notas:
- gd.documento NO almacena binarios (EP-018 entregará core.archivo_digital).
  Acá solo metadata + referencia por UUID a archivo_digital_id.
- versionado: cada nueva versión incrementa numero_version y actualiza
  version_vigente_id en gd.documento.
- descarga: registra siempre en gd.descarga_log (append-only); la URL
  pre-firmada la entregará EP-018.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


# Lista blanca de MIME types para gd.documento (GD-API-0058, RNF-046).
DOCUMENTO_MIME_WHITELIST = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',         # XLSX
    'application/vnd.openxmlformats-officedocument.presentationml.presentation', # PPTX
    'application/msword',
    'application/vnd.ms-excel',
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'text/plain', 'text/markdown',
}

DOCUMENTO_TAMANO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB

# Niveles de criticidad de descarga según clasificación.
CRITICIDAD_POR_CLASIFICACION = {
    'publica': 'baja',
    'interna': 'baja',
    'reservada': 'alta',
    'confidencial': 'alta',
    'datos_personales': 'alta',
    'sensible': 'alta',
}


def validar_archivo_para_documento(
    *, mime_type: str | None, tamano_bytes: int | None,
) -> None:
    """GD-API-0058: valida MIME + tamaño cuando archivo se usa como documento.

    Raises ValueError('mime_no_permitido') o ValueError('tamano_excedido').
    """
    if mime_type is not None and mime_type not in DOCUMENTO_MIME_WHITELIST:
        raise ValueError('mime_no_permitido')
    if tamano_bytes is not None and tamano_bytes > DOCUMENTO_TAMANO_MAX_BYTES:
        raise ValueError('tamano_excedido')


# =============================================================================
# CRUD documento + versiones (GD-API-0057, 0059)
# =============================================================================

async def crear_documento(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    titulo: str,
    descripcion: str | None,
    clasificacion_informacion: str,
    trd_serie_codigo: str | None,
    trd_subserie_codigo: str | None,
    trd_tipo_documental: str | None,
    archivo_digital_id: UUID,
    mime_type: str | None,
    tamano_bytes: int | None,
    hash_sha256: str | None,
    observaciones: str | None,
    creado_por_user_id: UUID,
) -> dict[str, Any]:
    """Crea documento + primera versión (numero_version=1, estado='borrador').

    Valida reglas suplementarias (GD-API-0058) sobre el archivo.
    """
    validar_archivo_para_documento(mime_type=mime_type, tamano_bytes=tamano_bytes)

    # 1. Crear documento sin version_vigente_id (FK deferred).
    doc_row = await conn.fetchrow(
        """
        insert into gd.documento (
            tenant_id, titulo, descripcion, clasificacion_informacion,
            trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
            estado, numero_version_vigente, creado_por_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, 'activo', 1, $8)
        returning id, titulo, descripcion, clasificacion_informacion,
                  trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
                  estado, version_vigente_id, numero_version_vigente,
                  anulado_en, motivo_anulacion, reemplazado_por_documento_id,
                  creado_por_user_id, created_at, updated_at
        """,
        tenant_id, titulo, descripcion, clasificacion_informacion,
        trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
        creado_por_user_id,
    )

    # 2. Crear primera versión.
    ver_row = await conn.fetchrow(
        """
        insert into gd.version_documento (
            tenant_id, documento_id, numero_version, archivo_digital_id,
            mime_type, tamano_bytes, hash_sha256, estado,
            creado_por_user_id, observaciones
        )
        values ($1, $2, 1, $3, $4, $5, $6, 'borrador', $7, $8)
        returning id, documento_id, numero_version, archivo_digital_id,
                  mime_type, tamano_bytes, hash_sha256, estado,
                  creado_por_user_id, aprobado_por_user_id, firmado_por_user_id,
                  observaciones, created_at
        """,
        tenant_id, doc_row['id'], archivo_digital_id,
        mime_type, tamano_bytes, hash_sha256,
        creado_por_user_id, observaciones,
    )

    # 3. Actualizar version_vigente_id en documento.
    doc_row = await conn.fetchrow(
        """
        update gd.documento set version_vigente_id = $2
        where id = $1
        returning id, titulo, descripcion, clasificacion_informacion,
                  trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
                  estado, version_vigente_id, numero_version_vigente,
                  anulado_en, motivo_anulacion, reemplazado_por_documento_id,
                  creado_por_user_id, created_at, updated_at
        """,
        doc_row['id'], ver_row['id'],
    )
    d = dict(doc_row)
    d['versiones'] = [dict(ver_row)]
    return d


async def obtener_documento(
    conn: asyncpg.Connection, *, tenant_id: UUID, documento_id: UUID,
) -> dict[str, Any] | None:
    doc_row = await conn.fetchrow(
        """
        select id, titulo, descripcion, clasificacion_informacion,
               trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
               estado, version_vigente_id, numero_version_vigente,
               anulado_en, motivo_anulacion, reemplazado_por_documento_id,
               creado_por_user_id, created_at, updated_at
        from gd.documento where id = $1 and tenant_id = $2
        """,
        documento_id, tenant_id,
    )
    if doc_row is None:
        return None
    versiones = await conn.fetch(
        """
        select id, documento_id, numero_version, archivo_digital_id,
               mime_type, tamano_bytes, hash_sha256, estado,
               creado_por_user_id, aprobado_por_user_id, firmado_por_user_id,
               observaciones, created_at
        from gd.version_documento
        where documento_id = $1 and tenant_id = $2
        order by numero_version desc
        """,
        documento_id, tenant_id,
    )
    d = dict(doc_row)
    d['versiones'] = [dict(v) for v in versiones]
    return d


async def listar_documentos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: list[str] | None = None,
    clasificacion: list[str] | None = None,
    trd_serie: str | None = None,
    titulo_like: str | None = None,
    limit: int = 50,
    permisos_clasificacion_permitidas: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Lista documentos con filtros.

    Si permisos_clasificacion_permitidas != None, solo retorna documentos
    cuya clasificacion_informacion está en la lista (RNF-053/0063).
    """
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = any(${len(params)}::text[])')
    if clasificacion:
        params.append(clasificacion)
        where.append(f'clasificacion_informacion = any(${len(params)}::text[])')
    if permisos_clasificacion_permitidas is not None:
        params.append(permisos_clasificacion_permitidas)
        where.append(
            f'clasificacion_informacion = any(${len(params)}::text[])'
        )
    if trd_serie:
        params.append(trd_serie)
        where.append(f'trd_serie_codigo = ${len(params)}')
    if titulo_like:
        params.append(f'%{titulo_like}%')
        where.append(f'titulo ilike ${len(params)}')
    params.append(limit)
    where_sql = ' and '.join(where)
    rows = await conn.fetch(
        f"""
        select id, titulo, clasificacion_informacion, estado,
               numero_version_vigente, trd_serie_codigo, creado_por_user_id,
               created_at
        from gd.documento
        where {where_sql}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_documentos(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> int:
    n = await conn.fetchval(
        'select count(*) from gd.documento where tenant_id = $1',
        tenant_id,
    )
    return int(n or 0)


async def nueva_version(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    archivo_digital_id: UUID,
    mime_type: str | None,
    tamano_bytes: int | None,
    hash_sha256: str | None,
    observaciones: str | None,
    creado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Crea nueva versión incrementando numero_version y actualizando vigente.

    Si documento está anulado/archivado/reemplazado → ValueError.
    """
    validar_archivo_para_documento(mime_type=mime_type, tamano_bytes=tamano_bytes)

    doc = await conn.fetchrow(
        'select estado, numero_version_vigente from gd.documento '
        'where id = $1 and tenant_id = $2',
        documento_id, tenant_id,
    )
    if doc is None:
        return None
    if doc['estado'] != 'activo':
        raise ValueError(f"estado_documento_invalido:{doc['estado']}")

    nuevo_num = doc['numero_version_vigente'] + 1
    ver_row = await conn.fetchrow(
        """
        insert into gd.version_documento (
            tenant_id, documento_id, numero_version, archivo_digital_id,
            mime_type, tamano_bytes, hash_sha256, estado,
            creado_por_user_id, observaciones
        )
        values ($1, $2, $3, $4, $5, $6, $7, 'borrador', $8, $9)
        returning id, documento_id, numero_version, archivo_digital_id,
                  mime_type, tamano_bytes, hash_sha256, estado,
                  creado_por_user_id, aprobado_por_user_id, firmado_por_user_id,
                  observaciones, created_at
        """,
        tenant_id, documento_id, nuevo_num, archivo_digital_id,
        mime_type, tamano_bytes, hash_sha256,
        creado_por_user_id, observaciones,
    )

    # Actualizar vigente en documento.
    await conn.execute(
        """
        update gd.documento
        set version_vigente_id = $3,
            numero_version_vigente = $4,
            actualizado_por_user_id = $5
        where id = $1 and tenant_id = $2
        """,
        documento_id, tenant_id, ver_row['id'], nuevo_num, creado_por_user_id,
    )
    return dict(ver_row)


async def listar_versiones(
    conn: asyncpg.Connection, *, tenant_id: UUID, documento_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, documento_id, numero_version, archivo_digital_id,
               mime_type, tamano_bytes, hash_sha256, estado,
               creado_por_user_id, aprobado_por_user_id, firmado_por_user_id,
               observaciones, created_at
        from gd.version_documento
        where documento_id = $1 and tenant_id = $2
        order by numero_version desc
        """,
        documento_id, tenant_id,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Anulación / reemplazo (GD-API-0062)
# =============================================================================

async def anular_documento(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    doc = await conn.fetchrow(
        'select estado from gd.documento where id = $1 and tenant_id = $2',
        documento_id, tenant_id,
    )
    if doc is None:
        return None
    if doc['estado'] == 'anulado':
        raise ValueError('ya_anulado')

    row = await conn.fetchrow(
        """
        update gd.documento
        set estado = 'anulado',
            anulado_en = now(),
            anulado_por_user_id = $3,
            motivo_anulacion = $4
        where id = $1 and tenant_id = $2
        returning id, titulo, descripcion, clasificacion_informacion,
                  trd_serie_codigo, trd_subserie_codigo, trd_tipo_documental,
                  estado, version_vigente_id, numero_version_vigente,
                  anulado_en, motivo_anulacion, reemplazado_por_documento_id,
                  creado_por_user_id, created_at, updated_at
        """,
        documento_id, tenant_id, usuario_actor_id, motivo,
    )
    d = dict(row)
    d['versiones'] = await listar_versiones(
        conn, tenant_id=tenant_id, documento_id=documento_id,
    )
    return d


async def reemplazar_documento(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    archivo_digital_id: UUID,
    motivo: str,
    mime_type: str | None,
    tamano_bytes: int | None,
    hash_sha256: str | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Crea nueva versión y marca la versión anterior vigente como 'reemplazada'."""
    validar_archivo_para_documento(mime_type=mime_type, tamano_bytes=tamano_bytes)

    doc = await conn.fetchrow(
        """
        select estado, version_vigente_id, numero_version_vigente
        from gd.documento where id = $1 and tenant_id = $2
        """,
        documento_id, tenant_id,
    )
    if doc is None:
        return None
    if doc['estado'] != 'activo':
        raise ValueError(f"estado_documento_invalido:{doc['estado']}")

    # Marcar versión anterior como reemplazada.
    if doc['version_vigente_id']:
        await conn.execute(
            "update gd.version_documento set estado = 'reemplazada' "
            "where id = $1 and tenant_id = $2",
            doc['version_vigente_id'], tenant_id,
        )

    nuevo_num = doc['numero_version_vigente'] + 1
    ver_row = await conn.fetchrow(
        """
        insert into gd.version_documento (
            tenant_id, documento_id, numero_version, archivo_digital_id,
            mime_type, tamano_bytes, hash_sha256, estado,
            creado_por_user_id, observaciones
        )
        values ($1, $2, $3, $4, $5, $6, $7, 'borrador', $8, $9)
        returning id, documento_id, numero_version, archivo_digital_id,
                  mime_type, tamano_bytes, hash_sha256, estado,
                  creado_por_user_id, aprobado_por_user_id, firmado_por_user_id,
                  observaciones, created_at
        """,
        tenant_id, documento_id, nuevo_num, archivo_digital_id,
        mime_type, tamano_bytes, hash_sha256,
        usuario_actor_id, f'Reemplazo: {motivo}',
    )

    await conn.execute(
        """
        update gd.documento
        set version_vigente_id = $3,
            numero_version_vigente = $4,
            actualizado_por_user_id = $5
        where id = $1 and tenant_id = $2
        """,
        documento_id, tenant_id, ver_row['id'], nuevo_num, usuario_actor_id,
    )
    return dict(ver_row)


# =============================================================================
# Anexos (GD-API-0060)
# =============================================================================

async def crear_anexo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_digital_id: UUID,
    entidad_relacionada_tipo: str,
    entidad_relacionada_id: UUID,
    titulo: str | None,
    descripcion: str | None,
    mime_type: str | None,
    tamano_bytes: int | None,
    creado_por_user_id: UUID,
) -> dict[str, Any]:
    # No aplicamos lista blanca a anexos (más permisivo que documento).
    row = await conn.fetchrow(
        """
        insert into gd.anexo (
            tenant_id, archivo_digital_id, entidad_relacionada_tipo,
            entidad_relacionada_id, titulo, descripcion, mime_type,
            tamano_bytes, creado_por_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        returning id, archivo_digital_id, entidad_relacionada_tipo,
                  entidad_relacionada_id, titulo, descripcion, mime_type,
                  tamano_bytes, creado_por_user_id, created_at
        """,
        tenant_id, archivo_digital_id, entidad_relacionada_tipo,
        entidad_relacionada_id, titulo, descripcion, mime_type,
        tamano_bytes, creado_por_user_id,
    )
    return dict(row)


async def listar_anexos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_tipo: str | None = None,
    entidad_id: UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if entidad_tipo:
        params.append(entidad_tipo)
        where.append(f'entidad_relacionada_tipo = ${len(params)}')
    if entidad_id:
        params.append(entidad_id)
        where.append(f'entidad_relacionada_id = ${len(params)}')
    params.append(limit)
    where_sql = ' and '.join(where)
    rows = await conn.fetch(
        f"""
        select id, archivo_digital_id, entidad_relacionada_tipo,
               entidad_relacionada_id, titulo, descripcion, mime_type,
               tamano_bytes, creado_por_user_id, created_at
        from gd.anexo
        where {where_sql}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_anexos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_tipo: str | None = None,
    entidad_id: UUID | None = None,
) -> int:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if entidad_tipo:
        params.append(entidad_tipo)
        where.append(f'entidad_relacionada_tipo = ${len(params)}')
    if entidad_id:
        params.append(entidad_id)
        where.append(f'entidad_relacionada_id = ${len(params)}')
    where_sql = ' and '.join(where)
    n = await conn.fetchval(
        f'select count(*) from gd.anexo where {where_sql}',
        *params,
    )
    return int(n or 0)


# =============================================================================
# Descarga auditada (GD-API-0061)
# =============================================================================

async def registrar_descarga(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_digital_id: UUID,
    usuario_id: UUID,
    documento_id: UUID | None = None,
    version_documento_id: UUID | None = None,
    contexto_tipo: str | None = None,
    contexto_id: UUID | None = None,
    clasificacion_informacion: str = 'interna',
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: UUID | None = None,
) -> dict[str, Any]:
    """Append a gd.descarga_log. Retorna {id, descargado_en, criticidad}."""
    row = await conn.fetchrow(
        """
        insert into gd.descarga_log (
            tenant_id, archivo_digital_id, documento_id, version_documento_id,
            contexto_tipo, contexto_id, clasificacion_informacion,
            usuario_id, ip, user_agent, request_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning id, descargado_en, clasificacion_informacion
        """,
        tenant_id, archivo_digital_id, documento_id, version_documento_id,
        contexto_tipo, contexto_id, clasificacion_informacion,
        usuario_id, ip, user_agent, request_id,
    )
    d = dict(row)
    d['criticidad'] = CRITICIDAD_POR_CLASIFICACION.get(
        d['clasificacion_informacion'], 'baja',
    )
    return d


# =============================================================================
# Relaciones polimórficas documento ↔ entidad
# =============================================================================

async def relacionar_documento(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
    entidad_tipo: str,
    entidad_id: UUID,
    rol: str | None,
    creado_por_user_id: UUID,
) -> dict[str, Any] | None:
    # Validar que documento existe.
    exists = await conn.fetchval(
        'select 1 from gd.documento where id = $1 and tenant_id = $2',
        documento_id, tenant_id,
    )
    if not exists:
        return None

    try:
        row = await conn.fetchrow(
            """
            insert into gd.documento_entidad_relacionada (
                tenant_id, documento_id, entidad_tipo, entidad_id, rol,
                creado_por_user_id
            )
            values ($1, $2, $3, $4, $5, $6)
            returning id, documento_id, entidad_tipo, entidad_id, rol,
                      creado_por_user_id, created_at
            """,
            tenant_id, documento_id, entidad_tipo, entidad_id, rol,
            creado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('relacion_ya_existe') from e
    return dict(row)


async def listar_relaciones(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    documento_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, documento_id, entidad_tipo, entidad_id, rol,
               creado_por_user_id, created_at
        from gd.documento_entidad_relacionada
        where documento_id = $1 and tenant_id = $2
        order by created_at desc
        """,
        documento_id, tenant_id,
    )
    return [dict(r) for r in rows]


__all__ = [
    # Constantes
    'DOCUMENTO_MIME_WHITELIST', 'DOCUMENTO_TAMANO_MAX_BYTES',
    'CRITICIDAD_POR_CLASIFICACION',
    # Validación
    'validar_archivo_para_documento',
    # Documento
    'crear_documento', 'obtener_documento', 'listar_documentos',
    'contar_documentos', 'nueva_version', 'listar_versiones',
    'anular_documento', 'reemplazar_documento',
    # Anexos
    'crear_anexo', 'listar_anexos', 'contar_anexos',
    # Descarga
    'registrar_descarga',
    # Relaciones
    'relacionar_documento', 'listar_relaciones',
]
