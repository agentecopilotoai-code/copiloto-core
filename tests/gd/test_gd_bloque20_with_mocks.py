"""Tests mocks para services del bloque 20 (utilidades EP-019/020)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import utilidades as svc


# =============================================================================
# Auditoría
# =============================================================================
class TestAuditoria:
    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_eventos_auditoria(conn)
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_todos_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_eventos_auditoria(
            conn, tenant_id=uuid4(),
            dominio='gd', tipo_evento='RadicadoCreado',
            actor_id=uuid4(), entidad_tipo='radicado', entidad_id=uuid4(),
            criticidad='alta',
            desde=datetime(2026, 1, 1), hasta=datetime(2026, 12, 31),
            limit=20,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_parsea_jsonb_str(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'id': uuid4(), 'tipo_evento': 'X', 'dominio': 'gd',
            'accion': 'crear', 'actor_type': 'user',
            'actor_id': uuid4(),
            'entidad_tipo': 'radicado', 'entidad_id': uuid4(),
            'criticidad': 'alta', 'request_id': None, 'ip': None,
            'valor_anterior': None, 'valor_nuevo': '{"x":1}',
            'justificacion': None, 'detalles': '{}',
            'created_at': datetime.now(),
        }]
        r = await svc.listar_eventos_auditoria(conn, tenant_id=uuid4())
        assert r[0]['valor_nuevo'] == {'x': 1}
        assert r[0]['detalles'] == {}

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_evento': 'X', 'dominio': 'gd',
            'accion': 'crear', 'actor_type': 'user', 'actor_id': uuid4(),
            'entidad_tipo': None, 'entidad_id': None,
            'criticidad': 'media', 'request_id': None, 'ip': None,
            'valor_anterior': None, 'valor_nuevo': None,
            'justificacion': None, 'detalles': {},
            'created_at': datetime.now(),
        }
        r = await svc.obtener_evento_auditoria(conn, evento_id=uuid4())
        assert r is not None

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_evento_auditoria(conn, evento_id=uuid4())
        assert r is None

    @pytest.mark.asyncio
    async def test_catalogo_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_catalogo_eventos(conn)
        assert r == []

    @pytest.mark.asyncio
    async def test_catalogo_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_catalogo_eventos(
            conn, dominio='gd', activo=True, limit=10,
        )
        assert r == []


# =============================================================================
# Constancia
# =============================================================================
class TestConstancia:
    def test_generar_codigo(self):
        c = svc.generar_codigo_verificacion()
        assert len(c) <= 20
        assert len(c) >= 10

    @pytest.mark.asyncio
    async def test_crear(self):
        conn = AsyncMock()
        cid = uuid4()
        conn.fetchrow.return_value = {
            'id': cid, 'codigo_verificacion': 'abc123',
            'qr_url_publica': '/gd/verificar/abc123',
            'fecha_generacion': datetime.now(),
            'exposicion_publica': True,
        }
        r = await svc.crear_constancia(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
            generada_por_user_id=uuid4(),
        )
        assert r['id'] == cid

    @pytest.mark.asyncio
    async def test_verificar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'exposicion_publica': True,
            'numero_radicado': '2026-E-001',
            'fecha_radicacion': datetime.now(),
            'tipo_radicado': 'entrada', 'estado': 'radicado',
            'asunto': 'Mi solicitud',
            'dependencia_nombre': 'Talento Humano',
        }
        conn.fetchval.return_value = True  # módulo activo
        r = await svc.verificar_constancia_publica(
            conn, codigo_verificacion='abc',
        )
        assert r['valida'] is True
        assert r['numero_radicado'] == '2026-E-001'

    @pytest.mark.asyncio
    async def test_verificar_asunto_largo_truncado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'exposicion_publica': True,
            'numero_radicado': '2026-E-001',
            'fecha_radicacion': datetime.now(),
            'tipo_radicado': 'entrada', 'estado': 'radicado',
            'asunto': 'X' * 200,
            'dependencia_nombre': 'Dep',
        }
        conn.fetchval.return_value = None  # módulo no configurado → activo
        r = await svc.verificar_constancia_publica(
            conn, codigo_verificacion='abc',
        )
        assert r['asunto_resumido'].endswith('...')

    @pytest.mark.asyncio
    async def test_verificar_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.verificar_constancia_publica(
            conn, codigo_verificacion='inexistente',
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_verificar_exposicion_off(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'exposicion_publica': False,
            'numero_radicado': 'X', 'fecha_radicacion': datetime.now(),
            'tipo_radicado': 'entrada', 'estado': 'X',
            'asunto': 'X', 'dependencia_nombre': 'X',
        }
        r = await svc.verificar_constancia_publica(
            conn, codigo_verificacion='abc',
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_verificar_modulo_desactivado(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tenant_id': uuid4(), 'exposicion_publica': True,
            'numero_radicado': 'X', 'fecha_radicacion': datetime.now(),
            'tipo_radicado': 'entrada', 'estado': 'X',
            'asunto': 'X', 'dependencia_nombre': 'X',
        }
        conn.fetchval.return_value = False
        r = await svc.verificar_constancia_publica(
            conn, codigo_verificacion='abc',
        )
        assert r is None


# =============================================================================
# Tipos doc identidad
# =============================================================================
class TestTiposDoc:
    @pytest.mark.asyncio
    async def test_catalogo_sin_pais(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_catalogo_tipos_doc(conn)
        assert r == []

    @pytest.mark.asyncio
    async def test_catalogo_con_pais(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_catalogo_tipos_doc(conn, pais_iso='CO')
        assert r == []

    @pytest.mark.asyncio
    async def test_org_listar(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_org_tipos_doc(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_patch_default_no_activo(self):
        conn = AsyncMock()
        with pytest.raises(ValueError, match='default_no_esta_activo'):
            await svc.patch_org_tipos_doc(
                conn, tenant_id=uuid4(),
                codigos_activos=['CC', 'CE'], codigo_default='NIT',
            )

    @pytest.mark.asyncio
    async def test_patch_codigo_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='codigo_no_existe'):
            await svc.patch_org_tipos_doc(
                conn, tenant_id=uuid4(),
                codigos_activos=['INEXISTENTE'], codigo_default=None,
            )

    @pytest.mark.asyncio
    async def test_patch_ok(self):
        conn = AsyncMock()
        # 2 validaciones existencia (CC, CE) + listar final
        conn.fetchval.return_value = 1  # ambos existen
        conn.fetch.return_value = []
        r = await svc.patch_org_tipos_doc(
            conn, tenant_id=uuid4(),
            codigos_activos=['CC', 'CE'], codigo_default='CC',
        )
        assert r == []


# =============================================================================
# Cambios dependencias
# =============================================================================
class TestCambiosDep:
    @pytest.mark.asyncio
    async def test_historial(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.historial_dependencia(
            conn, tenant_id=uuid4(), dependencia_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_fusionar_destino_no_existe(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(LookupError, match='dependencia_destino_no_existe'):
            await svc.fusionar_dependencias(
                conn, tenant_id=uuid4(),
                dependencias_origen=[uuid4()],
                dependencia_destino_id=uuid4(),
                fecha_vigencia=date.today(),
                motivo='X' * 11, acto_administrativo=None,
                registrado_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_fusionar_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 1  # destino existe
        # 2 origenes → 2 fetchrows + 1 fetchrow para destino = 3
        conn.fetchrow.side_effect = [
            {'id': uuid4()}, {'id': uuid4()}, {'id': uuid4()},
        ]
        r = await svc.fusionar_dependencias(
            conn, tenant_id=uuid4(),
            dependencias_origen=[uuid4(), uuid4()],
            dependencia_destino_id=uuid4(),
            fecha_vigencia=date.today(),
            motivo='fusión administrativa X' * 2,
            acto_administrativo='Decreto 123 de 2026',
            registrado_por_user_id=uuid4(),
        )
        assert len(r['relaciones_creadas']) == 3
        assert len(r['dependencias_cerradas']) == 2


# =============================================================================
# Contingencia
# =============================================================================
class TestContingencia:
    @pytest.mark.asyncio
    async def test_radicar(self):
        conn = AsyncMock()
        rad_id = uuid4()
        conn.fetchrow.return_value = {
            'id': rad_id, 'numero_radicado': 'MANUAL-001',
            'tipo_radicado': 'entrada',
            'fecha_radicacion': datetime.now(),
            'fecha_radicacion_real': datetime(2026, 5, 23, 10, 0),
            'es_radicacion_contingencia': True,
            'created_at': datetime.now(),
        }
        r = await svc.radicar_contingencia(
            conn, tenant_id=uuid4(),
            numero_radicado_manual='MANUAL-001',
            fecha_radicacion_real=datetime(2026, 5, 23, 10, 0),
            justificacion='caída del sistema 3 horas X' * 2,
            evidencia_contingencia_archivo_id=uuid4(),
            canal_id=uuid4(), tipo_radicado='entrada',
            asunto='Petición urgente',
            descripcion='Llegó en papel durante caída',
            tercero_id=None, dependencia_destino_id=None,
            usuario_actor_id=uuid4(),
        )
        assert r['es_radicacion_contingencia'] is True


# =============================================================================
# Hoja control + índice
# =============================================================================
class TestHojaControl:
    @pytest.mark.asyncio
    async def test_registrar_evento(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'expediente_id': uuid4(),
            'fecha': datetime.now(), 'evento': 'apertura',
            'descripcion': 'X', 'usuario_id': uuid4(),
            'snapshot_jsonb': {}, 'created_at': datetime.now(),
        }
        r = await svc.registrar_hoja_control(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            evento='apertura', descripcion='X', usuario_id=uuid4(),
            snapshot={'k': 'v'},
        )
        assert r['evento'] == 'apertura'

    @pytest.mark.asyncio
    async def test_registrar_jsonb_str(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'expediente_id': uuid4(),
            'fecha': datetime.now(), 'evento': 'cierre',
            'descripcion': None, 'usuario_id': uuid4(),
            'snapshot_jsonb': '{"x":1}', 'created_at': datetime.now(),
        }
        r = await svc.registrar_hoja_control(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            evento='cierre', descripcion=None, usuario_id=uuid4(),
        )
        assert r['snapshot_jsonb'] == {'x': 1}

    @pytest.mark.asyncio
    async def test_listar_vacio(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_hoja_control(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_str_parse(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{
            'id': uuid4(), 'expediente_id': uuid4(),
            'fecha': datetime.now(), 'evento': 'apertura',
            'descripcion': 'X', 'usuario_id': uuid4(),
            'snapshot_jsonb': '{"y":2}', 'created_at': datetime.now(),
        }]
        r = await svc.listar_hoja_control(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
        )
        assert r[0]['snapshot_jsonb'] == {'y': 2}

    @pytest.mark.asyncio
    async def test_indice_expediente_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.generar_indice_electronico(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            generado_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_indice_ok(self):
        conn = AsyncMock()
        # 1. exp existe (fetchval)
        # 2. max version (fetchval)
        # 3. items vinculados (fetch)
        # 4. hoja control (fetch)
        # 5. insert índice (fetchrow)
        conn.fetchval.side_effect = [1, 0]  # existe + max=0
        conn.fetch.side_effect = [
            [{'id': uuid4(), 'item_tipo': 'documento',
              'item_id': uuid4(), 'orden': 0}],
            [{'id': uuid4(), 'evento': 'apertura',
              'fecha': '2026-01-01T00:00:00'}],
        ]
        conn.fetchrow.return_value = {
            'id': uuid4(), 'expediente_id': uuid4(),
            'version_indice': 1, 'generado_en': datetime.now(),
            'generado_por_user_id': uuid4(),
            'contenido_jsonb': {}, 'hash_sha256': 'abc',
        }
        r = await svc.generar_indice_electronico(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            generado_por_user_id=uuid4(),
        )
        assert r['version_indice'] == 1

    @pytest.mark.asyncio
    async def test_indice_jsonb_str_parse(self):
        conn = AsyncMock()
        conn.fetchval.side_effect = [1, 0]
        conn.fetch.side_effect = [[], []]
        conn.fetchrow.return_value = {
            'id': uuid4(), 'expediente_id': uuid4(),
            'version_indice': 1, 'generado_en': datetime.now(),
            'generado_por_user_id': uuid4(),
            'contenido_jsonb': '{"x":1}', 'hash_sha256': 'a',
        }
        r = await svc.generar_indice_electronico(
            conn, tenant_id=uuid4(), expediente_id=uuid4(),
            generado_por_user_id=uuid4(),
        )
        assert r['contenido_jsonb'] == {'x': 1}
