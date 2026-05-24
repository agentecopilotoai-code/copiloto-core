"""Tests mocks para services del bloque 12 (firmas EP-011)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.gd.services import firmas as svc


def _esc_row(estado='pendiente_autorizacion', **extra):
    base = {
        'id': uuid4(), 'user_id': uuid4(), 'archivo_digital_id': uuid4(),
        'mime_type': 'image/png', 'tamano_bytes': 1024,
        'hash_sha256': 'abc', 'estado': estado,
        'autorizada_por_user_id': None, 'fecha_autorizacion': None,
        'motivo_revocacion': None, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


def _doc_firma_row(estado='consumada', tipo='electronica', **extra):
    base = {
        'id': uuid4(),
        'documento_id': uuid4(), 'version_documento_id': uuid4(),
        'firmante_user_id': uuid4(),
        'tipo_firma': tipo, 'estado': estado,
        'firma_escaneada_id': None, 'certificado_id': None,
        'proveedor_firma_digital': None,
        'hash_archivo': 'abc123', 'hash_algoritmo': 'sha256',
        'snapshot_firmante': {'user_id': 'x', 'email': 'u@x'},
        'ip': '1.2.3.4', 'user_agent': 'ua',
        'fecha_firma': datetime.now(),
        'fecha_rechazo': None, 'fecha_revocacion': None,
        'observaciones_rechazo': None, 'motivo_revocacion': None,
        'step_up_requerido': False, 'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Provider stub
# =============================================================================
class TestProvider:
    @pytest.mark.asyncio
    async def test_firmar_ok(self):
        p = svc.StubFirmaDigitalProvider()
        r = await p.firmar(
            archivo_bytes=b'data', certificado_id='cert1', pin='0000',
        )
        assert 'hash_archivo' in r
        assert r['firma_bytes'].startswith(b'STUB_SIGNATURE_')

    @pytest.mark.asyncio
    async def test_firmar_pin_invalido(self):
        p = svc.StubFirmaDigitalProvider()
        with pytest.raises(ValueError, match='pin_invalido'):
            await p.firmar(archivo_bytes=b'd', certificado_id='c', pin='wrong')

    @pytest.mark.asyncio
    async def test_firmar_cert_vacio(self):
        p = svc.StubFirmaDigitalProvider()
        with pytest.raises(ValueError, match='cert_no_valido'):
            await p.firmar(archivo_bytes=b'd', certificado_id='', pin='0000')

    @pytest.mark.asyncio
    async def test_validar_correcta(self):
        p = svc.StubFirmaDigitalProvider()
        sig = await p.firmar(archivo_bytes=b'data', certificado_id='c', pin='0000')
        assert await p.validar(
            archivo_bytes=b'data', firma_bytes=sig['firma_bytes'],
            certificado_id='c',
        )

    @pytest.mark.asyncio
    async def test_validar_falsa(self):
        p = svc.StubFirmaDigitalProvider()
        assert not await p.validar(
            archivo_bytes=b'data', firma_bytes=b'wrong', certificado_id='c',
        )

    def test_get_default_provider(self):
        p = svc.get_default_provider()
        assert isinstance(p, svc.StubFirmaDigitalProvider)


# =============================================================================
# Helpers
# =============================================================================
class TestHelpers:
    def test_calcular_hash(self):
        h = svc.calcular_hash_archivo(b'hello')
        assert len(h) == 64

    def test_step_up_sin_sesion(self):
        assert svc.requiere_step_up(None) is True

    def test_step_up_sesion_reciente(self):
        sesion = datetime.now(timezone.utc) - timedelta(minutes=2)
        assert svc.requiere_step_up(sesion) is False

    def test_step_up_sesion_antigua(self):
        sesion = datetime.now(timezone.utc) - timedelta(minutes=10)
        assert svc.requiere_step_up(sesion) is True

    def test_step_up_sin_tz(self):
        # datetime naive — debe tratarse como UTC
        sesion = datetime.utcnow() - timedelta(minutes=10)
        assert svc.requiere_step_up(sesion) is True


# =============================================================================
# Firma escaneada
# =============================================================================
class TestFirmaEscaneada:
    @pytest.mark.asyncio
    async def test_registrar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _esc_row()
        r = await svc.registrar_firma_escaneada(
            conn, tenant_id=uuid4(), user_id=uuid4(),
            archivo_digital_id=uuid4(),
            mime_type='image/png', tamano_bytes=1024, hash_sha256='abc',
        )
        assert r['estado'] == 'pendiente_autorizacion'

    @pytest.mark.asyncio
    async def test_registrar_duplicada(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = asyncpg.UniqueViolationError
        with pytest.raises(ValueError, match='firma_ya_registrada'):
            await svc.registrar_firma_escaneada(
                conn, tenant_id=uuid4(), user_id=uuid4(),
                archivo_digital_id=uuid4(),
                mime_type='image/png', tamano_bytes=None, hash_sha256=None,
            )

    @pytest.mark.asyncio
    async def test_autorizar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'user_id': uuid4(), 'estado': 'pendiente_autorizacion'},
            _esc_row(estado='activa'),
        ]
        r = await svc.autorizar_firma_escaneada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            autorizada_por_user_id=uuid4(),
        )
        assert r['estado'] == 'activa'

    @pytest.mark.asyncio
    async def test_autorizar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.autorizar_firma_escaneada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            autorizada_por_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_autorizar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'user_id': uuid4(), 'estado': 'activa',
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.autorizar_firma_escaneada(
                conn, tenant_id=uuid4(), firma_id=uuid4(),
                autorizada_por_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_revocar_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'activa'
        conn.fetchrow.return_value = _esc_row(estado='revocada',
                                                motivo_revocacion='X')
        r = await svc.revocar_firma_escaneada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            motivo='ya no se usa',
        )
        assert r['estado'] == 'revocada'

    @pytest.mark.asyncio
    async def test_revocar_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.revocar_firma_escaneada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            motivo='X' * 6,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_revocar_ya_revocada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'revocada'
        with pytest.raises(ValueError, match='ya_revocada'):
            await svc.revocar_firma_escaneada(
                conn, tenant_id=uuid4(), firma_id=uuid4(),
                motivo='X' * 6,
            )

    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_firmas_escaneadas(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_firmas_escaneadas(
            conn, tenant_id=uuid4(),
            user_id=uuid4(), estado='activa', limit=10,
        )
        assert r == []


# =============================================================================
# Validaciones internas
# =============================================================================
class TestValidaciones:
    @pytest.mark.asyncio
    async def test_validar_doc_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError, match='documento_o_version_no_existe'):
            await svc._validar_documento_firmable(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_validar_doc_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'doc_estado': 'anulado', 'ver_estado': 'aprobada',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        with pytest.raises(ValueError, match='documento_estado_invalido'):
            await svc._validar_documento_firmable(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_validar_ver_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'doc_estado': 'activo', 'ver_estado': 'borrador',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        with pytest.raises(ValueError, match='version_estado_invalido'):
            await svc._validar_documento_firmable(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_validar_firmante_inactivo(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'suspendido'
        with pytest.raises(ValueError, match='firmante_no_activo:suspendido'):
            await svc._validar_firmante_activo(
                conn, tenant_id=uuid4(), user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_validar_firmante_sin_perfil(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        with pytest.raises(ValueError, match='firmante_no_activo:sin_perfil'):
            await svc._validar_firmante_activo(
                conn, tenant_id=uuid4(), user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_capturar_snapshot_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'email': 'u@x', 'tipo_vinculacion': 'planta',
            'estado_gd': 'activo',
            'dependencia_actual_id': uuid4(), 'cargo_actual_id': uuid4(),
            'cargo_nombre': 'Director', 'dep_nombre': 'Talento',
        }
        s = await svc._capturar_snapshot_firmante(
            conn, tenant_id=uuid4(), user_id=uuid4(),
        )
        assert s['email'] == 'u@x'
        assert s['cargo_nombre'] == 'Director'

    @pytest.mark.asyncio
    async def test_capturar_snapshot_sin_perfil(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        uid = uuid4()
        s = await svc._capturar_snapshot_firmante(
            conn, tenant_id=uuid4(), user_id=uid,
        )
        assert s['snapshot_incompleto'] is True


# =============================================================================
# Firma electrónica documento
# =============================================================================
class TestFirmaElectronica:
    @pytest.mark.asyncio
    async def test_firmar_consumada_con_stepup_ok(self):
        conn = AsyncMock()
        # 1. validar doc + version
        # 2. validar firmante (fetchval)
        # 3. snapshot firmante
        # 4. insert firma
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _doc_firma_row(estado='consumada'),
        ]
        conn.fetchval.return_value = 'activo'
        r = await svc.firmar_documento_electronica(
            conn, tenant_id=uuid4(),
            documento_id=uuid4(), version_documento_id=uuid4(),
            firmante_user_id=uuid4(),
            sesion_iniciada_en=datetime.now(timezone.utc) - timedelta(minutes=2),
            step_up_satisfecho=False,
            ip='1.2.3.4', user_agent='ua',
        )
        assert r['estado'] == 'consumada'

    @pytest.mark.asyncio
    async def test_firmar_pendiente_stepup(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _doc_firma_row(estado='pendiente', step_up_requerido=True),
        ]
        conn.fetchval.return_value = 'activo'
        # Sesión muy vieja + sin step_up → pendiente
        r = await svc.firmar_documento_electronica(
            conn, tenant_id=uuid4(),
            documento_id=uuid4(), version_documento_id=uuid4(),
            firmante_user_id=uuid4(),
            sesion_iniciada_en=datetime.now(timezone.utc) - timedelta(minutes=30),
            step_up_satisfecho=False,
            ip=None, user_agent=None,
        )
        assert r['estado'] == 'pendiente'

    @pytest.mark.asyncio
    async def test_firmar_doc_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await svc.firmar_documento_electronica(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                sesion_iniciada_en=None, step_up_satisfecho=True,
                ip=None, user_agent=None,
            )

    @pytest.mark.asyncio
    async def test_firmar_firmante_inactivo(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'doc_estado': 'activo', 'ver_estado': 'aprobada',
            'archivo_digital_id': uuid4(), 'documento_id': uuid4(),
        }
        conn.fetchval.return_value = 'suspendido'
        with pytest.raises(ValueError, match='firmante_no_activo'):
            await svc.firmar_documento_electronica(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                sesion_iniciada_en=None, step_up_satisfecho=True,
                ip=None, user_agent=None,
            )


# =============================================================================
# Firma digital
# =============================================================================
class TestFirmaDigital:
    @pytest.mark.asyncio
    async def test_firmar_digital_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _doc_firma_row(tipo='digital', certificado_id='cert1',
                            proveedor_firma_digital='stub'),
        ]
        conn.fetchval.return_value = 'activo'
        r = await svc.firmar_documento_digital(
            conn, tenant_id=uuid4(),
            documento_id=uuid4(), version_documento_id=uuid4(),
            firmante_user_id=uuid4(),
            certificado_id='cert1', proveedor='stub', pin='0000',
            provider=None, ip=None, user_agent=None,
        )
        assert r['tipo_firma'] == 'digital'

    @pytest.mark.asyncio
    async def test_firmar_digital_pin_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
        ]
        conn.fetchval.return_value = 'activo'
        with pytest.raises(ValueError, match='pin_invalido'):
            await svc.firmar_documento_digital(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                certificado_id='cert1', proveedor='stub', pin='WRONG',
                provider=None, ip=None, user_agent=None,
            )


# =============================================================================
# Firma escaneada aplicada
# =============================================================================
class TestFirmaEscaneadaAplicada:
    @pytest.mark.asyncio
    async def test_firmar_escaneada_ok(self):
        conn = AsyncMock()
        firmante = uuid4()
        firma_esc_id = uuid4()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'user_id': firmante, 'estado': 'activa'},  # firma escaneada
            {'email': 'u@x', 'tipo_vinculacion': 'planta',
             'estado_gd': 'activo',
             'dependencia_actual_id': None, 'cargo_actual_id': None,
             'cargo_nombre': None, 'dep_nombre': None},
            _doc_firma_row(tipo='escaneada', firma_escaneada_id=firma_esc_id),
        ]
        conn.fetchval.return_value = 'activo'
        r = await svc.firmar_documento_escaneada(
            conn, tenant_id=uuid4(),
            documento_id=uuid4(), version_documento_id=uuid4(),
            firmante_user_id=firmante,
            firma_escaneada_id=firma_esc_id,
            ip=None, user_agent=None,
        )
        assert r['tipo_firma'] == 'escaneada'

    @pytest.mark.asyncio
    async def test_firmar_escaneada_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            None,  # firma escaneada
        ]
        conn.fetchval.return_value = 'activo'
        with pytest.raises(LookupError, match='firma_escaneada_no_existe'):
            await svc.firmar_documento_escaneada(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                firma_escaneada_id=uuid4(),
                ip=None, user_agent=None,
            )

    @pytest.mark.asyncio
    async def test_firmar_escaneada_no_activa(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'user_id': uuid4(), 'estado': 'revocada'},
        ]
        conn.fetchval.return_value = 'activo'
        with pytest.raises(ValueError, match='firma_escaneada_estado'):
            await svc.firmar_documento_escaneada(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                firma_escaneada_id=uuid4(),
                ip=None, user_agent=None,
            )

    @pytest.mark.asyncio
    async def test_firmar_escaneada_no_pertenece(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'doc_estado': 'activo', 'ver_estado': 'aprobada',
             'archivo_digital_id': uuid4(), 'documento_id': uuid4()},
            {'user_id': uuid4(), 'estado': 'activa'},  # otro user
        ]
        conn.fetchval.return_value = 'activo'
        with pytest.raises(ValueError, match='firma_escaneada_no_pertenece'):
            await svc.firmar_documento_escaneada(
                conn, tenant_id=uuid4(),
                documento_id=uuid4(), version_documento_id=uuid4(),
                firmante_user_id=uuid4(),
                firma_escaneada_id=uuid4(),
                ip=None, user_agent=None,
            )


# =============================================================================
# Rechazo / revocación / evidencia
# =============================================================================
class TestRechazoRevocacionEvidencia:
    @pytest.mark.asyncio
    async def test_rechazar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'estado': 'pendiente', 'firmante_user_id': uuid4()},
            _doc_firma_row(estado='rechazada'),
        ]
        r = await svc.rechazar_firma(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            observacion='no acepto', actor_user_id=uuid4(),
        )
        assert r['estado'] == 'rechazada'

    @pytest.mark.asyncio
    async def test_rechazar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.rechazar_firma(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            observacion='X' * 6, actor_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_rechazar_consumada(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'estado': 'consumada', 'firmante_user_id': uuid4(),
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.rechazar_firma(
                conn, tenant_id=uuid4(), firma_id=uuid4(),
                observacion='X' * 6, actor_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_revocar_consumada_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'consumada'
        conn.fetchrow.return_value = _doc_firma_row(estado='revocada')
        r = await svc.revocar_firma_consumada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            motivo='compromiso de seguridad', actor_user_id=uuid4(),
        )
        assert r['estado'] == 'revocada'

    @pytest.mark.asyncio
    async def test_revocar_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.revocar_firma_consumada(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
            motivo='X' * 11, actor_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_revocar_no_consumada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'pendiente'
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.revocar_firma_consumada(
                conn, tenant_id=uuid4(), firma_id=uuid4(),
                motivo='X' * 11, actor_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_obtener_evidencia_ok(self):
        conn = AsyncMock()
        row = _doc_firma_row()
        row['documento_titulo'] = 'Doc X'
        row['documento_version'] = 1
        conn.fetchrow.return_value = row
        r = await svc.obtener_evidencia(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
        )
        assert r['documento_titulo'] == 'Doc X'

    @pytest.mark.asyncio
    async def test_obtener_evidencia_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_evidencia(
            conn, tenant_id=uuid4(), firma_id=uuid4(),
        )
        assert r is None


# =============================================================================
# Listado
# =============================================================================
class TestListado:
    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_firmas_documento(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_firmas_documento(
            conn, tenant_id=uuid4(),
            documento_id=uuid4(), firmante_user_id=uuid4(),
            estado='consumada', limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_jsonb_str_parse(self):
        conn = AsyncMock()
        row = _doc_firma_row()
        row['snapshot_firmante'] = '{"user_id": "abc"}'
        conn.fetch.return_value = [row]
        r = await svc.listar_firmas_documento(
            conn, tenant_id=uuid4(),
        )
        assert r[0]['snapshot_firmante'] == {'user_id': 'abc'}
