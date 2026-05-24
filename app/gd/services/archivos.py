"""Services para EP-018 servicio transversal de archivos (bloque 19).

Cubre:
- IArchivoStorageProvider (filesystem stub, S3/Azure placeholders)
- IAntivirusScanner (stub permite todos excepto EICAR)
- IOCRProvider (stub determinista para PDF imágenes)
- subir/descargar/anular/listar archivos
- detectar_duplicado_por_hash
- aplicar_politica_retencion (worker)
- extraer_texto (dispatcher pypdf/tesseract/openpyxl según mime)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg


# =============================================================================
# Constantes
# =============================================================================

# Mime types que típicamente requieren OCR.
MIME_OCR_CANDIDATES = {
    'image/jpeg', 'image/png', 'image/tiff', 'image/gif', 'image/webp',
}
PDF_OCR_HEURISTICA_MIN_CHARS_POR_PAGINA = 50

EICAR_SIGNATURE = (
    'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
)

UMBRAL_BAJA_CONFIANZA_OCR = 0.6


# =============================================================================
# Storage providers
# =============================================================================

class IArchivoStorageProvider(ABC):
    """Almacenamiento de bytes (filesystem, S3, Azure Blob)."""

    @abstractmethod
    async def save(
        self, *, tenant_id: UUID, key: str, contenido: bytes,
    ) -> str:
        """Guarda contenido bajo key. Retorna ruta efectiva."""
        ...

    @abstractmethod
    async def get(self, *, key: str) -> bytes | None:
        """Retorna contenido o None si no existe."""
        ...

    @abstractmethod
    async def delete(self, *, key: str) -> bool:
        """Elimina key. True si se eliminó, False si no existía."""
        ...

    @abstractmethod
    async def exists(self, *, key: str) -> bool:
        ...

    @abstractmethod
    async def generar_url_descarga(
        self, *, key: str, ttl_segundos: int = 300,
    ) -> str:
        """Genera URL pre-firmada o token de descarga."""
        ...


class InMemoryStorageProvider(IArchivoStorageProvider):
    """Storage en memoria para tests."""

    def __init__(self):
        self._files: dict[str, bytes] = {}

    async def save(self, *, tenant_id, key, contenido):
        self._files[key] = contenido
        return f'memory://{key}'

    async def get(self, *, key):
        return self._files.get(key)

    async def delete(self, *, key):
        if key in self._files:
            del self._files[key]
            return True
        return False

    async def exists(self, *, key):
        return key in self._files

    async def generar_url_descarga(self, *, key, ttl_segundos=300):
        return f'/core/archivos/_download/{key}?ttl={ttl_segundos}'


class FilesystemStorageProvider(IArchivoStorageProvider):
    """Stub filesystem. En producción debería ir bajo
    `app/core/files/storage.py` con la lógica real del repositorio.
    """

    def __init__(self, base_dir: str = '/tmp/gd_storage'):
        self.base_dir = base_dir

    def _path(self, key: str) -> str:
        return os.path.join(self.base_dir, key)

    async def save(self, *, tenant_id, key, contenido):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_bytes(contenido)
        return f'file://{path}'

    async def get(self, *, key):
        path = self._path(key)
        if not os.path.exists(path):
            return None
        return Path(path).read_bytes()

    async def delete(self, *, key):
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    async def exists(self, *, key):
        return os.path.exists(self._path(key))

    async def generar_url_descarga(self, *, key, ttl_segundos=300):
        return f'/core/archivos/_download/{key}?ttl={ttl_segundos}'


_default_storage: IArchivoStorageProvider = InMemoryStorageProvider()


def get_default_storage() -> IArchivoStorageProvider:
    return _default_storage


def set_default_storage(provider: IArchivoStorageProvider) -> None:
    """Permite swap del provider (tests / config en bootstrap)."""
    global _default_storage
    _default_storage = provider


# =============================================================================
# Antivirus
# =============================================================================

class IAntivirusScanner(ABC):
    @abstractmethod
    async def scan(self, *, contenido: bytes) -> dict[str, Any]:
        """Retorna {limpio: bool, motor: str, detalle: str|None}."""
        ...


class StubAntivirusScanner(IAntivirusScanner):
    """Bloquea solo el EICAR test string (RNF-046)."""

    MOTOR = 'stub-eicar'

    async def scan(self, *, contenido):
        es_eicar = EICAR_SIGNATURE.encode() in contenido
        if es_eicar:
            return {'limpio': False, 'motor': self.MOTOR,
                     'detalle': 'EICAR test signature detected'}
        return {'limpio': True, 'motor': self.MOTOR, 'detalle': None}


_default_antivirus: IAntivirusScanner = StubAntivirusScanner()


def get_default_antivirus() -> IAntivirusScanner:
    return _default_antivirus


# =============================================================================
# OCR
# =============================================================================

class IOCRProvider(ABC):
    @abstractmethod
    async def ocr(
        self, *, contenido: bytes, mime_type: str,
        idiomas: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retorna {texto_completo, paginas, confianza, motor, version}."""
        ...


class StubOCRProvider(IOCRProvider):
    """Stub determinista para tests: extrae nombre del archivo + size."""

    MOTOR = 'stub-tesseract'
    VERSION = '0.1.0-stub'

    async def ocr(self, *, contenido, mime_type, idiomas=None):
        # Determinista: hash mod 10 / 10.
        h = int(hashlib.sha256(contenido).hexdigest()[:8], 16)
        confianza = 0.5 + (h % 50) / 100.0  # entre 0.50 y 0.99
        texto = (
            f"[OCR STUB] {mime_type} de {len(contenido)} bytes - "
            f"contenido extraído simulado para pruebas."
        )
        return {
            'texto_completo': texto,
            'paginas': [{'numero': 1, 'texto': texto,
                          'confianza': confianza}],
            'confianza': confianza,
            'motor': self.MOTOR,
            'version': self.VERSION,
        }


_default_ocr: IOCRProvider = StubOCRProvider()


def get_default_ocr() -> IOCRProvider:
    return _default_ocr


# =============================================================================
# Helpers
# =============================================================================

def calcular_sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def calcular_md5(contenido: bytes) -> str:
    return hashlib.md5(contenido).hexdigest()


def detectar_extension(nombre_archivo: str) -> str | None:
    """Extrae extensión del nombre. Lower-case, sin punto."""
    if '.' not in nombre_archivo:
        return None
    return nombre_archivo.rsplit('.', 1)[-1].lower()


def calcular_fecha_purga(
    *, fecha_referencia: datetime, retencion_politica: str,
) -> datetime | None:
    """Calcula fecha elegible para purga según política.

    Para v1, valores hardcoded:
    - 'eliminacion': 5 años después
    - 'seleccion': 10 años después
    - 'estandar': 7 años después
    - 'conservacion_total': None (nunca)
    - 'reproduccion': 15 años después
    """
    plazos_anos = {
        'estandar': 7,
        'eliminacion': 5,
        'seleccion': 10,
        'reproduccion': 15,
    }
    if retencion_politica == 'conservacion_total':
        return None
    if retencion_politica not in plazos_anos:
        return None
    return fecha_referencia + timedelta(days=365 * plazos_anos[retencion_politica])


# =============================================================================
# Subir archivo (GD-API-0110)
# =============================================================================

async def subir_archivo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    nombre_original: str,
    mime_type: str,
    contenido: bytes,
    proposito: str,
    contexto_entidad_tipo: str | None,
    contexto_entidad_id: UUID | None,
    retencion_politica: str | None,
    storage_backend: str,
    encriptado_at_rest: bool,
    cargado_por_user_id: UUID,
    storage_provider: IArchivoStorageProvider | None = None,
    antivirus_scanner: IAntivirusScanner | None = None,
) -> dict[str, Any]:
    """Sube archivo: calcula hashes + ejecuta antivirus + persiste binario
    + registra metadata en core.archivo_digital.

    Si antivirus detecta infección → estado='bloqueado'.
    """
    pv = storage_provider or get_default_storage()
    av = antivirus_scanner or get_default_antivirus()

    sha256 = calcular_sha256(contenido)
    md5 = calcular_md5(contenido)
    extension = detectar_extension(nombre_original)

    # Antivirus.
    av_result = await av.scan(contenido=contenido)
    av_estado = 'limpio' if av_result['limpio'] else 'infectado'
    archivo_estado = 'cargado' if av_result['limpio'] else 'bloqueado'

    # Generar key + persistir binario (solo si pasa antivirus).
    archivo_id = uuid4()
    key = f"{tenant_id}/{archivo_id}/{nombre_original}"
    ruta = None
    if av_result['limpio']:
        ruta = await pv.save(tenant_id=tenant_id, key=key, contenido=contenido)

    # Calcular fecha purga.
    fecha_purga = None
    if retencion_politica:
        fecha_purga = calcular_fecha_purga(
            fecha_referencia=datetime.now(timezone.utc),
            retencion_politica=retencion_politica,
        )

    row = await conn.fetchrow(
        """
        insert into core.archivo_digital (
            id, tenant_id, nombre_original, extension, mime_type, tamano_bytes,
            hash_sha256, hash_md5, storage_backend, ruta_almacenamiento,
            encriptado_at_rest, proposito, contexto_entidad_tipo,
            contexto_entidad_id, estado, analisis_antivirus, motor_antivirus,
            fecha_antivirus, detalle_antivirus, retencion_politica,
            fecha_elegible_purga, cargado_por_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, now(), $18, $19, $20, $21)
        returning id, nombre_original, extension, mime_type, tamano_bytes,
                  hash_sha256, hash_md5, storage_backend, ruta_almacenamiento,
                  encriptado_at_rest, proposito, contexto_entidad_tipo,
                  contexto_entidad_id, estado, analisis_antivirus,
                  motor_antivirus, fecha_antivirus, detalle_antivirus,
                  retencion_politica, fecha_elegible_purga, fecha_purga_bytes,
                  motivo_purga, cargado_por_user_id, cargado_en,
                  ultimo_acceso_en, total_descargas, metadata
        """,
        archivo_id, tenant_id, nombre_original, extension, mime_type,
        len(contenido), sha256, md5, storage_backend, ruta,
        encriptado_at_rest, proposito, contexto_entidad_tipo,
        contexto_entidad_id, archivo_estado, av_estado,
        av_result['motor'], av_result.get('detalle'),
        retencion_politica, fecha_purga, cargado_por_user_id,
    )
    d = dict(row)
    if isinstance(d.get('metadata'), str):
        d['metadata'] = json.loads(d['metadata'])
    return d


# =============================================================================
# Lectura / listado
# =============================================================================

async def obtener_archivo(
    conn: asyncpg.Connection, *, tenant_id: UUID, archivo_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, nombre_original, extension, mime_type, tamano_bytes,
               hash_sha256, hash_md5, storage_backend, ruta_almacenamiento,
               encriptado_at_rest, proposito, contexto_entidad_tipo,
               contexto_entidad_id, estado, analisis_antivirus,
               motor_antivirus, fecha_antivirus, detalle_antivirus,
               retencion_politica, fecha_elegible_purga, fecha_purga_bytes,
               motivo_purga, cargado_por_user_id, cargado_en,
               ultimo_acceso_en, total_descargas, metadata
        from core.archivo_digital where id = $1 and tenant_id = $2
        """,
        archivo_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get('metadata'), str):
        d['metadata'] = json.loads(d['metadata'])
    return d


async def listar_archivos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    proposito: str | None = None,
    estado: str | None = None,
    contexto_entidad_tipo: str | None = None,
    contexto_entidad_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if proposito:
        params.append(proposito)
        where.append(f'proposito = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if contexto_entidad_tipo:
        params.append(contexto_entidad_tipo)
        where.append(f'contexto_entidad_tipo = ${len(params)}')
    if contexto_entidad_id:
        params.append(contexto_entidad_id)
        where.append(f'contexto_entidad_id = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, nombre_original, extension, mime_type, tamano_bytes,
               hash_sha256, hash_md5, storage_backend, ruta_almacenamiento,
               encriptado_at_rest, proposito, contexto_entidad_tipo,
               contexto_entidad_id, estado, analisis_antivirus,
               motor_antivirus, fecha_antivirus, detalle_antivirus,
               retencion_politica, fecha_elegible_purga, fecha_purga_bytes,
               motivo_purga, cargado_por_user_id, cargado_en,
               ultimo_acceso_en, total_descargas, metadata
        from core.archivo_digital
        where {' and '.join(where)}
        order by cargado_en desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get('metadata'), str):
            d['metadata'] = json.loads(d['metadata'])
        out.append(d)
    return out


# =============================================================================
# Descargar (registra log + actualiza contador)
# =============================================================================

async def descargar_archivo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_id: UUID,
    usuario_id: UUID,
    motivo: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: UUID | None = None,
    identidad_tecnica_id: UUID | None = None,
    storage_provider: IArchivoStorageProvider | None = None,
) -> dict[str, Any] | None:
    """Genera URL pre-firmada + log de descarga.

    Si archivo bloqueado/anulado/purgado → ValueError.
    """
    arch = await obtener_archivo(
        conn, tenant_id=tenant_id, archivo_id=archivo_id,
    )
    if arch is None:
        return None
    if arch['estado'] not in ('cargado', 'extrayendo', 'listo'):
        raise ValueError(f"estado_invalido:{arch['estado']}")
    if arch['analisis_antivirus'] == 'infectado':
        raise ValueError('archivo_infectado')

    pv = storage_provider or get_default_storage()
    key = f"{tenant_id}/{archivo_id}/{arch['nombre_original']}"

    # Generar URL (provider en stub la simula).
    url = await pv.generar_url_descarga(key=key, ttl_segundos=300)

    # Registrar log.
    log_row = await conn.fetchrow(
        """
        insert into core.archivo_descarga_log (
            tenant_id, archivo_digital_id, usuario_id, identidad_tecnica_id,
            motivo, ip, user_agent, request_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning id, descargado_en
        """,
        tenant_id, archivo_id, usuario_id, identidad_tecnica_id,
        motivo, ip, user_agent, request_id,
    )

    # Actualizar contador (best-effort).
    await conn.execute(
        """
        update core.archivo_digital
        set total_descargas = total_descargas + 1,
            ultimo_acceso_en = now()
        where id = $1 and tenant_id = $2
        """,
        archivo_id, tenant_id,
    )

    return {
        'archivo_id': archivo_id,
        'descarga_id': log_row['id'],
        'descargado_en': log_row['descargado_en'],
        'download_url': url,
        'expira_en': datetime.now(timezone.utc) + timedelta(seconds=300),
        'requiere_antivirus_check': arch['analisis_antivirus'] == 'pendiente',
    }


# =============================================================================
# Anular archivo
# =============================================================================

async def anular_archivo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    arch = await conn.fetchrow(
        'select estado from core.archivo_digital where id = $1 and tenant_id = $2',
        archivo_id, tenant_id,
    )
    if arch is None:
        return None
    if arch['estado'] == 'anulado':
        raise ValueError('ya_anulado')

    await conn.execute(
        """
        update core.archivo_digital
        set estado = 'anulado',
            metadata = metadata || jsonb_build_object(
                'anulado_en', now()::text,
                'anulado_por', $3::text,
                'motivo_anulacion', $4
            )
        where id = $1 and tenant_id = $2
        """,
        archivo_id, tenant_id, str(usuario_actor_id), motivo,
    )
    return await obtener_archivo(
        conn, tenant_id=tenant_id, archivo_id=archivo_id,
    )


# =============================================================================
# Dedupe (GD-API-0113)
# =============================================================================

async def buscar_duplicados_por_hash(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    hash_sha256: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, nombre_original, extension, mime_type, tamano_bytes,
               hash_sha256, hash_md5, storage_backend, ruta_almacenamiento,
               encriptado_at_rest, proposito, contexto_entidad_tipo,
               contexto_entidad_id, estado, analisis_antivirus,
               motor_antivirus, fecha_antivirus, detalle_antivirus,
               retencion_politica, fecha_elegible_purga, fecha_purga_bytes,
               motivo_purga, cargado_por_user_id, cargado_en,
               ultimo_acceso_en, total_descargas, metadata
        from core.archivo_digital
        where tenant_id = $1 and hash_sha256 = $2
          and estado not in ('anulado', 'purgado')
        order by cargado_en desc
        limit $3
        """,
        tenant_id, hash_sha256, limit,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get('metadata'), str):
            d['metadata'] = json.loads(d['metadata'])
        out.append(d)
    return out


# =============================================================================
# Extracción texto / OCR (GD-API-0111/0112)
# =============================================================================

async def extraer_texto(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_id: UUID,
    forzar: bool = False,
    motor_preferido: str | None = None,
    storage_provider: IArchivoStorageProvider | None = None,
    ocr_provider: IOCRProvider | None = None,
) -> dict[str, Any] | None:
    """Extrae texto de un archivo según mime type. Idempotente por
    (archivo_id, motor) salvo `forzar=True`."""
    arch = await obtener_archivo(
        conn, tenant_id=tenant_id, archivo_id=archivo_id,
    )
    if arch is None:
        return None
    if arch['estado'] not in ('cargado', 'extrayendo', 'listo'):
        raise ValueError(f"estado_invalido:{arch['estado']}")

    # Decidir motor.
    if motor_preferido and motor_preferido != 'auto':
        motor = motor_preferido
    elif arch['mime_type'] in MIME_OCR_CANDIDATES:
        motor = 'tesseract'
    elif arch['mime_type'] == 'application/pdf':
        motor = 'pypdf'  # heurística: caller marcará para OCR si <50 chars/page
    elif arch['mime_type'] in (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
    ):
        motor = 'openpyxl'
    else:
        motor = 'texto_plano'

    # Verificar idempotencia.
    if not forzar:
        existing = await conn.fetchval(
            """
            select id from core.extraccion_resultado
            where archivo_digital_id = $1 and tenant_id = $2 and motor = $3
            """,
            archivo_id, tenant_id, _motor_canonical(motor),
        )
        if existing:
            return await obtener_extraccion(
                conn, tenant_id=tenant_id, extraccion_id=existing,
            )

    pv = storage_provider or get_default_storage()
    key = f"{tenant_id}/{archivo_id}/{arch['nombre_original']}"
    contenido = await pv.get(key=key)
    if contenido is None:
        raise LookupError('contenido_no_disponible')

    t0 = time.monotonic()
    motor_real = _motor_canonical(motor)
    confianza = None
    paginas: list[dict[str, Any]] = []
    texto = ''
    warning = False
    truncado = False
    motivo_truncado = None

    if motor == 'tesseract':
        ocr = ocr_provider or get_default_ocr()
        r = await ocr.ocr(
            contenido=contenido, mime_type=arch['mime_type'],
            idiomas=['spa', 'eng'],
        )
        texto = r['texto_completo']
        paginas = r['paginas']
        confianza = r['confianza']
        motor_real = f"{r['motor']}-v{r['version']}"
        warning = confianza is not None and confianza < UMBRAL_BAJA_CONFIANZA_OCR
    elif motor == 'pypdf':
        # Stub: heurística texto vacío → recomendaría OCR
        texto = f'[PDF text extraction stub] {arch["nombre_original"]}'
        paginas = [{'numero': 1, 'texto': texto, 'confianza': None}]
    elif motor == 'openpyxl':
        texto = f'[XLSX extraction stub] {arch["nombre_original"]}'
        paginas = [{'numero_hoja': 1, 'nombre_hoja': 'Hoja1',
                     'headers': [], 'rows': []}]
        # Política de truncado.
        if arch['tamano_bytes'] > 50 * 1024 * 1024:
            truncado = True
            motivo_truncado = 'tamano_excedido'
    elif motor == 'texto_plano':
        texto = contenido.decode('utf-8', errors='replace')[:100_000]
        if len(contenido) > 100_000:
            truncado = True
            motivo_truncado = 'truncado_a_100k_chars'

    duracion_ms = int((time.monotonic() - t0) * 1000)

    # Upsert: si ya existe (cuando forzar=True), insert+ON CONFLICT update.
    row = await conn.fetchrow(
        """
        insert into core.extraccion_resultado (
            tenant_id, archivo_digital_id, motor, version, texto_completo,
            paginas_jsonb, confianza, warning_baja_confianza, truncado,
            motivo_truncado, duracion_ms
        )
        values ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11)
        on conflict (archivo_digital_id, motor) do update set
            texto_completo = excluded.texto_completo,
            paginas_jsonb = excluded.paginas_jsonb,
            confianza = excluded.confianza,
            warning_baja_confianza = excluded.warning_baja_confianza,
            truncado = excluded.truncado,
            motivo_truncado = excluded.motivo_truncado,
            duracion_ms = excluded.duracion_ms,
            extraido_en = now()
        returning id, archivo_digital_id, motor, version, texto_completo,
                  paginas_jsonb, confianza, warning_baja_confianza,
                  truncado, motivo_truncado, extraido_en, duracion_ms
        """,
        tenant_id, archivo_id, motor_real,
        (StubOCRProvider.VERSION if motor == 'tesseract' else None),
        texto, json.dumps(paginas), confianza, warning, truncado,
        motivo_truncado, duracion_ms,
    )
    d = dict(row)
    d['paginas'] = d.pop('paginas_jsonb')
    if isinstance(d.get('paginas'), str):
        d['paginas'] = json.loads(d['paginas'])
    return d


def _motor_canonical(motor: str) -> str:
    """Para idempotencia por (archivo, motor), normalizamos motor cuando
    venga sin version. Para tesseract guardamos sólo 'tesseract' como
    clave de unique para evitar duplicados por versión menor."""
    if motor.startswith('tesseract') or motor == 'tesseract':
        return 'tesseract'
    return motor


async def obtener_extraccion(
    conn: asyncpg.Connection, *, tenant_id: UUID, extraccion_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, archivo_digital_id, motor, version, texto_completo,
               paginas_jsonb, confianza, warning_baja_confianza,
               truncado, motivo_truncado, extraido_en, duracion_ms
        from core.extraccion_resultado where id = $1 and tenant_id = $2
        """,
        extraccion_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    d['paginas'] = d.pop('paginas_jsonb')
    if isinstance(d.get('paginas'), str):
        d['paginas'] = json.loads(d['paginas'])
    return d


# =============================================================================
# Retención (GD-API-0114)
# =============================================================================

async def aplicar_politica_retencion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dry_run: bool = True,
    limit: int = 100,
    storage_provider: IArchivoStorageProvider | None = None,
) -> dict[str, Any]:
    """Worker de retención: identifica archivos elegibles para purga.

    Solo purga bytes — metadata se preserva (RNF-010). Marca
    `estado='purgado'`, `ruta_almacenamiento=NULL`, `fecha_purga_bytes=now()`.
    Si `retencion_politica='conservacion_total'` → nunca purga.
    """
    pv = storage_provider or get_default_storage()

    # Candidatos: con fecha_elegible_purga <= now, todavía con bytes.
    rows = await conn.fetch(
        """
        select id, ruta_almacenamiento, retencion_politica,
               nombre_original
        from core.archivo_digital
        where tenant_id = $1
          and fecha_elegible_purga is not null
          and fecha_elegible_purga <= now()
          and ruta_almacenamiento is not null
          and estado not in ('purgado', 'anulado')
          and (retencion_politica is null
               or retencion_politica != 'conservacion_total')
        limit $2
        """,
        tenant_id, limit,
    )

    candidatos = list(rows)
    purgados = 0
    saltados = 0
    detalle: list[dict[str, Any]] = []

    for r in candidatos:
        if dry_run:
            detalle.append({
                'id': str(r['id']),
                'nombre': r['nombre_original'],
                'accion': 'purgaria',
                'politica': r['retencion_politica'],
            })
            continue

        # Intentar borrar bytes.
        try:
            key_relativa = r['ruta_almacenamiento'].split('://')[-1]
            await pv.delete(key=key_relativa)
            await conn.execute(
                """
                update core.archivo_digital
                set estado = 'purgado',
                    ruta_almacenamiento = null,
                    fecha_purga_bytes = now(),
                    motivo_purga = 'retencion_aplicada'
                where id = $1 and tenant_id = $2
                """,
                r['id'], tenant_id,
            )
            purgados += 1
            detalle.append({
                'id': str(r['id']), 'nombre': r['nombre_original'],
                'accion': 'purgado',
            })
        except Exception as e:
            saltados += 1
            detalle.append({
                'id': str(r['id']), 'nombre': r['nombre_original'],
                'accion': 'error', 'error': str(e)[:200],
            })

    return {
        'dry_run': dry_run,
        'candidatos_evaluados': len(candidatos),
        'purgados': purgados,
        'saltados': saltados,
        'detalle': detalle,
    }


# =============================================================================
# attach_proposito (helper para callers que ya tienen archivo creado)
# =============================================================================

async def attach_proposito(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    archivo_id: UUID,
    proposito: str,
    contexto_entidad_tipo: str | None,
    contexto_entidad_id: UUID | None,
) -> dict[str, Any] | None:
    """Actualiza propósito + contexto de un archivo existente."""
    exists = await conn.fetchval(
        'select estado from core.archivo_digital '
        'where id = $1 and tenant_id = $2',
        archivo_id, tenant_id,
    )
    if exists is None:
        return None
    if exists in ('anulado', 'purgado'):
        raise ValueError(f"estado_invalido:{exists}")

    await conn.execute(
        """
        update core.archivo_digital
        set proposito = $3,
            contexto_entidad_tipo = $4,
            contexto_entidad_id = $5
        where id = $1 and tenant_id = $2
        """,
        archivo_id, tenant_id, proposito,
        contexto_entidad_tipo, contexto_entidad_id,
    )
    return await obtener_archivo(
        conn, tenant_id=tenant_id, archivo_id=archivo_id,
    )


__all__ = [
    # Constantes
    'MIME_OCR_CANDIDATES', 'EICAR_SIGNATURE',
    'UMBRAL_BAJA_CONFIANZA_OCR',
    # Providers
    'IArchivoStorageProvider', 'InMemoryStorageProvider',
    'FilesystemStorageProvider', 'get_default_storage', 'set_default_storage',
    'IAntivirusScanner', 'StubAntivirusScanner', 'get_default_antivirus',
    'IOCRProvider', 'StubOCRProvider', 'get_default_ocr',
    # Helpers
    'calcular_sha256', 'calcular_md5', 'detectar_extension',
    'calcular_fecha_purga',
    # CRUD
    'subir_archivo', 'obtener_archivo', 'listar_archivos',
    'descargar_archivo', 'anular_archivo',
    # Dedupe
    'buscar_duplicados_por_hash',
    # Extracción / OCR
    'extraer_texto', 'obtener_extraccion',
    # Retención
    'aplicar_politica_retencion',
    # Helpers callers
    'attach_proposito',
]
