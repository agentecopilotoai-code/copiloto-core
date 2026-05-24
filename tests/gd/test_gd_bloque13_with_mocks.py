"""Tests mocks para services del bloque 13 (correo institucional EP-012)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import correo as svc


def _bz_row(estado='activa', **extra):
    base = {
        'id': uuid4(), 'nombre': 'Buzón principal',
        'direccion_correo': 'inbox@org.gov.co',
        'proveedor': 'imap_generico',
        'dependencia_id': None,
        'host': 'imap.org.gov.co', 'port': 993, 'usar_tls': True,
        'usuario_smtp': 'inbox@org.gov.co',
        'config': {}, 'secret_vault_ref': 'vault/buzon-1',
        'ultima_lectura_en': None,
        'envio_acuse_recibido': False, 'plantilla_acuse_id': None,
        'estado': estado, 'ultimo_error_texto': None, 'ultimo_error_en': None,
        'created_at': datetime.now(), 'updated_at': datetime.now(),
    }
    base.update(extra)
    return base


def _correo_row(estado='pendiente', **extra):
    base = {
        'id': uuid4(), 'buzon_id': uuid4(),
        'message_id': 'msg-1@example',
        'remitente_email': 'sender@example.com',
        'remitente_nombre': 'Alice',
        'destinatarios_to': ['inbox@org.gov.co'],
        'destinatarios_cc': [], 'destinatarios_bcc': [],
        'asunto': 'Solicitud info', 'cuerpo_texto': 'Hola',
        'cuerpo_html': None, 'fecha_envio_original': datetime.now(),
        'importado_en': datetime.now(),
        'anexos_archivo_ids': [],
        'estado': estado, 'radicado_id': None,
        'convertido_por_user_id': None, 'fecha_decision': None,
        'motivo_descarte': None, 'observaciones': None,
        'acuse_enviado_en': None, 'acuse_estado': None,
    }
    base.update(extra)
    return base


# =============================================================================
# Provider stub
# =============================================================================
class TestProvider:
    @pytest.mark.asyncio
    async def test_test_conexion_ok(self):
        p = svc.StubMailProvider()
        r = await p.test_conexion(
            host='h', port=993, usar_tls=True, usuario='u',
            secret_vault_ref='vault/x', config={},
        )
        assert r['exitoso'] is True

    @pytest.mark.asyncio
    async def test_test_conexion_credenciales_invalidas(self):
        p = svc.StubMailProvider()
        r = await p.test_conexion(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='invalid', config={},
        )
        assert r['exitoso'] is False

    @pytest.mark.asyncio
    async def test_descargar_correos_sin_seed(self):
        p = svc.StubMailProvider()
        r = await p.descargar_correos(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='vault/x', config={},
            desde_message_id=None, max_correos=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_descargar_correos_con_seed(self):
        p = svc.StubMailProvider()
        seed = [
            {'message_id': 'm1', 'remitente_email': 'a@x.com', 'asunto': 'Hi'},
            {'message_id': 'm2', 'remitente_email': 'b@x.com'},
        ]
        r = await p.descargar_correos(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='vault/x', config={'seed_correos': seed},
            desde_message_id=None, max_correos=10,
        )
        assert len(r) == 2
        assert r[0].message_id == 'm1'

    @pytest.mark.asyncio
    async def test_descargar_respeta_max(self):
        p = svc.StubMailProvider()
        seed = [{'message_id': f'm{i}'} for i in range(20)]
        r = await p.descargar_correos(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='vault/x', config={'seed_correos': seed},
            desde_message_id=None, max_correos=5,
        )
        assert len(r) == 5

    @pytest.mark.asyncio
    async def test_enviar_acuse_ok(self):
        p = svc.StubMailProvider()
        r = await p.enviar_acuse(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='vault/x', config={},
            destinatario='x@y.com', asunto='Acuse', cuerpo_texto='OK',
        )
        assert r['exitoso'] is True

    @pytest.mark.asyncio
    async def test_enviar_acuse_falla(self):
        p = svc.StubMailProvider()
        r = await p.enviar_acuse(
            host=None, port=None, usar_tls=False, usuario=None,
            secret_vault_ref='invalid', config={},
            destinatario='x@y.com', asunto='Acuse', cuerpo_texto='OK',
        )
        assert r['exitoso'] is False

    def test_get_default(self):
        assert isinstance(svc.get_default_provider(), svc.StubMailProvider)


# =============================================================================
# CRUD buzón
# =============================================================================
class TestBuzon:
    @pytest.mark.asyncio
    async def test_crear_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row()
        r = await svc.crear_buzon(
            conn, tenant_id=uuid4(), nombre='Buzón',
            direccion_correo='x@y.com', proveedor='imap_generico',
            dependencia_id=None, host='h', port=993, usar_tls=True,
            usuario_smtp='u', config={},
            secret_vault_ref='vault/x', envio_acuse_recibido=False,
            plantilla_acuse_id=None, created_by_user_id=uuid4(),
        )
        assert r['proveedor'] == 'imap_generico'

    @pytest.mark.asyncio
    async def test_crear_duplicado(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='direccion_correo_ya_registrada'):
            await svc.crear_buzon(
                conn, tenant_id=uuid4(), nombre='X',
                direccion_correo='dup@x.com', proveedor='gmail_api',
                dependencia_id=None, host=None, port=None, usar_tls=True,
                usuario_smtp=None, config={},
                secret_vault_ref='v', envio_acuse_recibido=False,
                plantilla_acuse_id=None, created_by_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_crear_config_jsonb_str(self):
        # config returned as JSON string
        conn = AsyncMock()
        row = _bz_row()
        row['config'] = '{"k": "v"}'
        conn.fetchrow.return_value = row
        r = await svc.crear_buzon(
            conn, tenant_id=uuid4(), nombre='X',
            direccion_correo='y@x.com', proveedor='pop3',
            dependencia_id=None, host=None, port=None, usar_tls=True,
            usuario_smtp=None, config={'k': 'v'},
            secret_vault_ref='v', envio_acuse_recibido=False,
            plantilla_acuse_id=None, created_by_user_id=uuid4(),
        )
        assert r['config'] == {'k': 'v'}

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row()
        r = await svc.obtener_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_obtener_config_jsonb_str(self):
        conn = AsyncMock()
        row = _bz_row()
        row['config'] = '{}'
        conn.fetchrow.return_value = row
        r = await svc.obtener_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
        )
        assert r['config'] == {}

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_buzones(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_buzones(
            conn, tenant_id=uuid4(),
            estado='activa', dependencia_id=uuid4(), limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_config_str_parse(self):
        conn = AsyncMock()
        row = _bz_row()
        row['config'] = '{"x": 1}'
        conn.fetch.return_value = [row]
        r = await svc.listar_buzones(conn, tenant_id=uuid4())
        assert r[0]['config'] == {'x': 1}

    @pytest.mark.asyncio
    async def test_patch_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        # patch calls obtener_buzon → uses fetchrow
        conn.fetchrow.return_value = _bz_row(nombre='Nuevo')
        r = await svc.patch_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            cambios={'nombre': 'Nuevo', 'config': {'k': 'v'}},
        )
        assert r['nombre'] == 'Nuevo'

    @pytest.mark.asyncio
    async def test_patch_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.patch_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            cambios={'nombre': 'X'},
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_patch_sin_cambios(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1
        conn.fetchrow.return_value = _bz_row()
        r = await svc.patch_buzon(
            conn, tenant_id=uuid4(), buzon_id=uuid4(), cambios={},
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_probar_conexion_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row()
        r = await svc.probar_conexion(
            conn, tenant_id=uuid4(), buzon_id=uuid4(), provider=None,
        )
        assert r['exitoso'] is True

    @pytest.mark.asyncio
    async def test_probar_conexion_falla_actualiza_estado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row(secret_vault_ref='invalid')
        r = await svc.probar_conexion(
            conn, tenant_id=uuid4(), buzon_id=uuid4(), provider=None,
        )
        assert r['exitoso'] is False

    @pytest.mark.asyncio
    async def test_probar_conexion_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.probar_conexion(
            conn, tenant_id=uuid4(), buzon_id=uuid4(), provider=None,
        )
        assert r is None


# =============================================================================
# Worker (GD-API-0074)
# =============================================================================
class TestWorker:
    @pytest.mark.asyncio
    async def test_worker_buzon_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.ejecutar_worker(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            max_correos=10, provider=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_worker_buzon_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row(estado='inactiva')
        with pytest.raises(ValueError, match='buzon_estado_invalido'):
            await svc.ejecutar_worker(
                conn, tenant_id=uuid4(), buzon_id=uuid4(),
                max_correos=10, provider=None,
            )

    @pytest.mark.asyncio
    async def test_worker_sin_correos(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _bz_row()
        r = await svc.ejecutar_worker(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            max_correos=10, provider=None,
        )
        assert r['correos_descargados'] == 0
        assert r['correos_nuevos'] == 0

    @pytest.mark.asyncio
    async def test_worker_descarga_y_persiste(self):
        conn = AsyncMock()
        bz = _bz_row(config={'seed_correos': [
            {'message_id': 'm1', 'remitente_email': 'a@x.com'},
            {'message_id': 'm2', 'remitente_email': 'b@x.com'},
        ]})
        # fetchrow: 1 for obtener_buzon + 2 for inserts
        conn.fetchrow.side_effect = [
            bz, {'id': uuid4()}, {'id': uuid4()},
        ]
        r = await svc.ejecutar_worker(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            max_correos=10, provider=None,
        )
        assert r['correos_nuevos'] == 2
        assert r['correos_duplicados_omitidos'] == 0

    @pytest.mark.asyncio
    async def test_worker_idempotente_duplicados(self):
        conn = AsyncMock()
        bz = _bz_row(config={'seed_correos': [
            {'message_id': 'dup1', 'remitente_email': 'a@x.com'},
            {'message_id': 'dup2', 'remitente_email': 'b@x.com'},
        ]})
        # Ambos inserts duplicados
        conn.fetchrow.side_effect = [
            bz, asyncpg.UniqueViolationError, asyncpg.UniqueViolationError,
        ]
        r = await svc.ejecutar_worker(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            max_correos=10, provider=None,
        )
        assert r['correos_nuevos'] == 0
        assert r['correos_duplicados_omitidos'] == 2

    @pytest.mark.asyncio
    async def test_worker_errores_genericos(self):
        conn = AsyncMock()
        bz = _bz_row(config={'seed_correos': [
            {'message_id': 'e1', 'remitente_email': 'a@x.com'},
        ]})
        conn.fetchrow.side_effect = [bz, RuntimeError('db down')]
        r = await svc.ejecutar_worker(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
            max_correos=10, provider=None,
        )
        assert r['errores'] == 1


# =============================================================================
# Correos importados
# =============================================================================
class TestCorreoOps:
    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _correo_row()
        r = await svc.obtener_correo(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_correo(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_correos(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_correos(
            conn, tenant_id=uuid4(),
            buzon_id=uuid4(), estado='pendiente',
            remitente_email='a@x.com', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_sin_buzon(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 5
        assert await svc.contar_correos(conn, tenant_id=uuid4()) == 5

    @pytest.mark.asyncio
    async def test_contar_con_buzon(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 3
        assert await svc.contar_correos(
            conn, tenant_id=uuid4(), buzon_id=uuid4(),
        ) == 3

    @pytest.mark.asyncio
    async def test_asociar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},  # select estado
            _correo_row(estado='asociado_radicado'),  # update returning
        ]
        conn.fetchval.return_value = 1  # radicado exists
        r = await svc.asociar_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            radicado_id=uuid4(), observaciones='ok',
            usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'asociado_radicado'

    @pytest.mark.asyncio
    async def test_asociar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.asociar_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            radicado_id=uuid4(), observaciones=None,
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_asociar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'descartado'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.asociar_a_radicado(
                conn, tenant_id=uuid4(), correo_id=uuid4(),
                radicado_id=uuid4(), observaciones=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_asociar_radicado_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'pendiente'}
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='radicado_no_existe'):
            await svc.asociar_a_radicado(
                conn, tenant_id=uuid4(), correo_id=uuid4(),
                radicado_id=uuid4(), observaciones=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_descartar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente'},
            _correo_row(estado='descartado', motivo_descarte='spam'),
        ]
        r = await svc.descartar_correo(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            motivo='spam evidente', usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'descartado'

    @pytest.mark.asyncio
    async def test_descartar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.descartar_correo(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            motivo='X' * 11, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_descartar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'estado': 'convertido_radicado'}
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.descartar_correo(
                conn, tenant_id=uuid4(), correo_id=uuid4(),
                motivo='X' * 11, usuario_actor_id=uuid4(),
            )


# =============================================================================
# Convertir correo a radicado (orquesta svc_terceros + svc_radicados)
# =============================================================================
class TestConvertir:
    @pytest.mark.asyncio
    async def test_convertir_correo_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override=None, descripcion=None,
            tercero_id=None, crear_tercero=False,
            dependencia_destino_id=None, enviar_acuse=False,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_convertir_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'estado': 'descartado', 'buzon_id': uuid4(),
            'remitente_email': 'a@x.com', 'remitente_nombre': None,
            'asunto': None, 'cuerpo_texto': None,
            'envio_acuse_recibido': False, 'host': None, 'port': None,
            'usar_tls': True, 'usuario_smtp': None,
            'secret_vault_ref': 'v', 'config': {},
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.convertir_a_radicado(
                conn, tenant_id=uuid4(), correo_id=uuid4(),
                canal_id=uuid4(),
                asunto_override=None, descripcion=None,
                tercero_id=None, crear_tercero=False,
                dependencia_destino_id=None, enviar_acuse=False,
                usuario_actor_id=uuid4(), provider=None,
            )

    @pytest.mark.asyncio
    async def test_convertir_ok_sin_acuse(self, monkeypatch):
        # Mock svc_radicados.crear_radicado
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-99'}
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )

        conn = AsyncMock()
        # 1. select estado/buzon (con join)
        # 2. obtener_correo (after update)
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'a@x.com', 'remitente_nombre': None,
             'asunto': 'Sub', 'cuerpo_texto': 'body',
             'envio_acuse_recibido': False, 'host': None, 'port': None,
             'usar_tls': True, 'usuario_smtp': None,
             'secret_vault_ref': 'v', 'config': {}},
            _correo_row(estado='convertido_radicado', radicado_id=rad_id),
        ]
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override=None, descripcion=None,
            tercero_id=None, crear_tercero=False,
            dependencia_destino_id=None, enviar_acuse=False,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r['radicado_id'] == rad_id
        assert r['acuse_estado'] == 'no_aplica'

    @pytest.mark.asyncio
    async def test_convertir_ok_con_acuse_exitoso(self, monkeypatch):
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-100'}
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'a@x.com', 'remitente_nombre': 'Alice',
             'asunto': 'Hi', 'cuerpo_texto': 'body',
             'envio_acuse_recibido': True, 'host': 'h', 'port': 587,
             'usar_tls': True, 'usuario_smtp': 'u',
             'secret_vault_ref': 'vault/ok', 'config': {}},
            _correo_row(estado='convertido_radicado', radicado_id=rad_id,
                         acuse_estado='enviado'),
        ]
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override='Override', descripcion='Desc',
            tercero_id=uuid4(), crear_tercero=False,
            dependencia_destino_id=uuid4(), enviar_acuse=True,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r['acuse_estado'] == 'enviado'

    @pytest.mark.asyncio
    async def test_convertir_ok_acuse_falla(self, monkeypatch):
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-101'}
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'a@x.com', 'remitente_nombre': None,
             'asunto': None, 'cuerpo_texto': None,
             'envio_acuse_recibido': True, 'host': None, 'port': None,
             'usar_tls': True, 'usuario_smtp': None,
             # secret_vault_ref='invalid' → stub provider falla
             'secret_vault_ref': 'invalid', 'config': {}},
            _correo_row(estado='convertido_radicado', acuse_estado='error'),
        ]
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override=None, descripcion=None,
            tercero_id=None, crear_tercero=False,
            dependencia_destino_id=None, enviar_acuse=True,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r['acuse_estado'] == 'error'

    @pytest.mark.asyncio
    async def test_convertir_con_crear_tercero(self, monkeypatch):
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-200'}
        async def fake_crear_tercero(conn, **kwargs):
            return {'id': uuid4()}
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )
        monkeypatch.setattr(
            'app.gd.services.terceros.crear_tercero', fake_crear_tercero,
        )
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'new@x.com', 'remitente_nombre': 'New Person',
             'asunto': None, 'cuerpo_texto': None,
             'envio_acuse_recibido': False, 'host': None, 'port': None,
             'usar_tls': True, 'usuario_smtp': None,
             'secret_vault_ref': 'v', 'config': {}},
            _correo_row(estado='convertido_radicado'),
        ]
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override=None, descripcion=None,
            tercero_id=None, crear_tercero=True,
            dependencia_destino_id=None, enviar_acuse=False,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r['radicado_id'] == rad_id

    @pytest.mark.asyncio
    async def test_convertir_crear_tercero_falla(self, monkeypatch):
        rad_id = uuid4()
        async def fake_crear_rad(conn, **kwargs):
            return {'id': rad_id, 'numero_radicado': '2026-E-201'}
        async def fake_crear_tercero(conn, **kwargs):
            raise RuntimeError('duplicado o falla')
        monkeypatch.setattr(
            'app.gd.services.radicados.crear_radicado', fake_crear_rad,
        )
        monkeypatch.setattr(
            'app.gd.services.terceros.crear_tercero', fake_crear_tercero,
        )
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'buzon_id': uuid4(),
             'remitente_email': 'fail@x.com', 'remitente_nombre': None,
             'asunto': None, 'cuerpo_texto': None,
             'envio_acuse_recibido': False, 'host': None, 'port': None,
             'usar_tls': True, 'usuario_smtp': None,
             'secret_vault_ref': 'v', 'config': {}},
            _correo_row(estado='convertido_radicado'),
        ]
        # tercero falla pero continúa con None
        r = await svc.convertir_a_radicado(
            conn, tenant_id=uuid4(), correo_id=uuid4(),
            canal_id=uuid4(),
            asunto_override=None, descripcion=None,
            tercero_id=None, crear_tercero=True,
            dependencia_destino_id=None, enviar_acuse=False,
            usuario_actor_id=uuid4(), provider=None,
        )
        assert r['radicado_id'] == rad_id
