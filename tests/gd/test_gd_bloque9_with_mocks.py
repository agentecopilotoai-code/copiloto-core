"""Tests mocks para services del bloque 9 (correspondencia EP-008)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services import correspondencia as svc


# Helper: row de gd.correspondencia base.
def _corresp_row(
    estado='borrador', tipo='interna',
    usuario_proyecta=None, **extra,
):
    base = {
        'id': uuid4(), 'tipo': tipo,
        'dependencia_origen_id': uuid4(),
        'dependencia_destino_id': None,
        'tercero_remitente_id': None,
        'radicado_entrada_id': None, 'radicado_salida_id': None,
        'documento_principal_id': None, 'plantilla_id': None,
        'asunto': 'A', 'contenido_borrador': 'X',
        'prioridad': 'normal', 'requiere_respuesta': False,
        'fecha_limite_respuesta': None, 'estado': estado,
        'usuario_proyecta_id': usuario_proyecta or uuid4(),
        'usuario_revisa_id': None, 'usuario_aprueba_id': None,
        'usuario_firma_id': None, 'usuario_envio_id': None,
        'fecha_envio': None, 'fecha_aprobacion': None,
        'fecha_firma': None, 'fecha_radicacion': None,
        'observaciones_devolucion': None,
        'canal_envio_id': None, 'soporte_envio_uri': None,
        'soporte_envio_codigo_rastreo': None, 'fecha_registro_soporte': None,
        'anulada_en': None, 'motivo_anulacion': None,
        'correspondencia_padre_id': None,
        'created_at': datetime.now(),
    }
    base.update(extra)
    return base


# =============================================================================
# Helpers internos
# =============================================================================
class TestHelpers:
    @pytest.mark.asyncio
    async def test_validar_regla_misma_dependencia(self):
        conn = AsyncMock()
        # Misma dependencia: NO consulta (cortocircuito).
        dep = uuid4()
        await svc._validar_regla_comunicacion(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=dep, dependencia_destino_id=dep,
        )
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_validar_regla_permitida(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'permitido': True}
        await svc._validar_regla_comunicacion(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(), dependencia_destino_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_validar_regla_no_existe(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None  # default permisivo
        await svc._validar_regla_comunicacion(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(), dependencia_destino_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_validar_regla_prohibida(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'permitido': False}
        with pytest.raises(ValueError, match='comunicacion_no_permitida'):
            await svc._validar_regla_comunicacion(
                conn, tenant_id=uuid4(),
                dependencia_origen_id=uuid4(), dependencia_destino_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_listar_destinatarios(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc._listar_destinatarios(conn, correspondencia_id=uuid4())
        assert r == []


# =============================================================================
# Interna (GD-API-0052)
# =============================================================================
class TestInterna:
    @pytest.mark.asyncio
    async def test_crear_interna_ok_inmediato(self):
        conn = AsyncMock()
        # Regla permitida (1 destinatario dep) + insert corresp + insert destinatario
        conn.fetchrow.side_effect = [
            {'permitido': True},  # validar regla
            _corresp_row(estado='enviada'),  # insert
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.crear_interna(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='Test', contenido_borrador='msg',
            prioridad='normal', requiere_respuesta=False,
            fecha_limite_respuesta=None,
            documento_principal_id=None, plantilla_id=None,
            destinatarios=[{'tipo_destinatario': 'dependencia',
                             'dependencia_id': uuid4(),
                             'tipo_copia': 'principal'}],
            usuario_proyecta_id=uuid4(),
            enviar_inmediato=True,
        )
        assert r['estado'] == 'enviada'
        assert len(r['destinatarios']) == 1

    @pytest.mark.asyncio
    async def test_crear_interna_borrador(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'permitido': True},
            _corresp_row(estado='borrador'),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.crear_interna(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='T', contenido_borrador=None,
            prioridad='alta', requiere_respuesta=True,
            fecha_limite_respuesta=datetime.now(),
            documento_principal_id=uuid4(), plantilla_id=uuid4(),
            destinatarios=[{'tipo_destinatario': 'dependencia',
                             'dependencia_id': uuid4(),
                             'tipo_copia': 'principal'}],
            usuario_proyecta_id=uuid4(),
            enviar_inmediato=False,
        )
        assert r['estado'] == 'borrador'

    @pytest.mark.asyncio
    async def test_crear_interna_multiples_destinatarios(self):
        conn = AsyncMock()
        # 2 destinatarios → 2 validaciones + 1 insert + 2 inserts dest
        conn.fetchrow.side_effect = [
            {'permitido': True}, {'permitido': True},  # 2 validaciones
            _corresp_row(estado='enviada'),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'copia',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.crear_interna(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='X', contenido_borrador=None,
            prioridad='normal', requiere_respuesta=False,
            fecha_limite_respuesta=None,
            documento_principal_id=None, plantilla_id=None,
            destinatarios=[
                {'tipo_destinatario': 'dependencia',
                 'dependencia_id': uuid4(), 'tipo_copia': 'principal'},
                {'tipo_destinatario': 'dependencia',
                 'dependencia_id': uuid4(), 'tipo_copia': 'copia'},
            ],
            usuario_proyecta_id=uuid4(), enviar_inmediato=True,
        )
        assert len(r['destinatarios']) == 2

    @pytest.mark.asyncio
    async def test_crear_interna_regla_prohibida(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'permitido': False}
        with pytest.raises(ValueError, match='comunicacion_no_permitida'):
            await svc.crear_interna(
                conn, tenant_id=uuid4(),
                dependencia_origen_id=uuid4(),
                asunto='X', contenido_borrador=None,
                prioridad='normal', requiere_respuesta=False,
                fecha_limite_respuesta=None,
                documento_principal_id=None, plantilla_id=None,
                destinatarios=[{'tipo_destinatario': 'dependencia',
                                 'dependencia_id': uuid4(),
                                 'tipo_copia': 'principal'}],
                usuario_proyecta_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_marcar_leida_ok(self):
        conn = AsyncMock()
        dest_id = uuid4()
        # fetchrow: dest pendiente, fetchval: 0 pendientes, fetchrow obtener_corresp + dest
        conn.fetchrow.side_effect = [
            {'id': dest_id},
            _corresp_row(estado='leida'),
        ]
        conn.fetchval.return_value = 0  # todos leídos
        conn.fetch.return_value = []
        r = await svc.marcar_leida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'leida'

    @pytest.mark.asyncio
    async def test_marcar_leida_no_destinatario(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.marcar_leida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_marcar_leida_pendientes(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4()},
            _corresp_row(estado='enviada'),
        ]
        conn.fetchval.return_value = 1  # 1 pendiente todavía
        conn.fetch.return_value = []
        r = await svc.marcar_leida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r is not None

    @pytest.mark.asyncio
    async def test_responder_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'dependencia_origen_id': uuid4(), 'tipo': 'interna',
             'estado': 'enviada'},
            _corresp_row(tipo='interna', estado='enviada'),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.responder(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='RE: X', contenido_borrador='resp',
            documento_principal_id=None,
            usuario_proyecta_id=uuid4(), enviar_inmediato=True,
        )
        assert r['estado'] == 'enviada'

    @pytest.mark.asyncio
    async def test_responder_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.responder(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='X', contenido_borrador=None,
            documento_principal_id=None,
            usuario_proyecta_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_responder_tipo_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'dependencia_origen_id': uuid4(),
            'tipo': 'externa_recibida', 'estado': 'derivada',
        }
        with pytest.raises(ValueError, match='solo_interna_admite_respuesta'):
            await svc.responder(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                dependencia_origen_id=uuid4(),
                asunto='X', contenido_borrador=None,
                documento_principal_id=None,
                usuario_proyecta_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_reenviar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'asunto': 'X', 'contenido_borrador': 'msg',
             'documento_principal_id': None, 'tipo': 'interna'},
            {'permitido': True},  # validar regla
            _corresp_row(tipo='interna', estado='enviada'),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.reenviar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_origen_id=uuid4(),
            destinatarios=[{'tipo_destinatario': 'dependencia',
                             'dependencia_id': uuid4(),
                             'tipo_copia': 'principal'}],
            usuario_proyecta_id=uuid4(), observaciones='FYI',
        )
        assert r['estado'] == 'enviada'

    @pytest.mark.asyncio
    async def test_reenviar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.reenviar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            dependencia_origen_id=uuid4(),
            destinatarios=[{'tipo_destinatario': 'dependencia',
                             'dependencia_id': uuid4(),
                             'tipo_copia': 'principal'}],
            usuario_proyecta_id=uuid4(), observaciones=None,
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_reenviar_tipo_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'asunto': 'X', 'contenido_borrador': 'msg',
            'documento_principal_id': None, 'tipo': 'externa_enviada',
        }
        with pytest.raises(ValueError, match='solo_interna_admite_reenvio'):
            await svc.reenviar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                dependencia_origen_id=uuid4(),
                destinatarios=[{'tipo_destinatario': 'dependencia',
                                 'dependencia_id': uuid4(),
                                 'tipo_copia': 'principal'}],
                usuario_proyecta_id=uuid4(), observaciones=None,
            )


# =============================================================================
# Externa recibida (GD-API-0053)
# =============================================================================
class TestExternaRecibida:
    @pytest.mark.asyncio
    async def test_crear_desde_radicado_externa_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None  # no existe
        conn.fetchrow.side_effect = [
            {'asunto': 'A', 'descripcion': 'D',
             'tercero_id': uuid4(), 'dependencia_destino_id': uuid4(),
             'usuario_radicador_id': uuid4()},
            _corresp_row(tipo='externa_recibida', estado='derivada',
                          radicado_entrada_id=uuid4()),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'dependencia',
             'dependencia_id': uuid4(), 'tercero_id': None,
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.crear_desde_radicado_externa(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r['tipo'] == 'externa_recibida'

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_idempotente(self):
        conn = AsyncMock()
        conn.fetchval.return_value = uuid4()  # ya existe
        r = await svc.crear_desde_radicado_externa(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_no_radicado(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetchrow.return_value = None
        r = await svc.crear_desde_radicado_externa(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_crear_desde_radicado_sin_dependencia(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetchrow.side_effect = [
            {'asunto': 'A', 'descripcion': 'D',
             'tercero_id': uuid4(), 'dependencia_destino_id': None,
             'usuario_radicador_id': uuid4()},
            _corresp_row(tipo='externa_recibida', estado='derivada'),
        ]
        r = await svc.crear_desde_radicado_externa(
            conn, tenant_id=uuid4(), radicado_id=uuid4(),
        )
        assert r['destinatarios'] == []

    @pytest.mark.asyncio
    async def test_gestionar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'tipo': 'externa_recibida', 'estado': 'derivada'},
            _corresp_row(tipo='externa_recibida', estado='gestionada'),
            _corresp_row(tipo='externa_recibida', estado='gestionada'),  # obtener
        ]
        conn.fetch.return_value = []
        r = await svc.gestionar_externa_recibida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            observaciones='gestionada por mí',
            dependencia_id=uuid4(), usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'gestionada'

    @pytest.mark.asyncio
    async def test_gestionar_tipo_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'tipo': 'interna', 'estado': 'enviada'}
        with pytest.raises(ValueError, match='tipo_invalido'):
            await svc.gestionar_externa_recibida(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                observaciones='x', dependencia_id=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_gestionar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tipo': 'externa_recibida', 'estado': 'anulada',
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.gestionar_externa_recibida(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                observaciones='x', dependencia_id=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_gestionar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.gestionar_externa_recibida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            observaciones='x', dependencia_id=None,
            usuario_actor_id=uuid4(),
        )
        assert r is None


# =============================================================================
# Workflow externa enviada (GD-API-0054)
# =============================================================================
class TestWorkflowExterna:
    @pytest.mark.asyncio
    async def test_crear_borrador_externa(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            _corresp_row(tipo='externa_enviada', estado='borrador'),
            {'id': uuid4(), 'correspondencia_id': uuid4(),
             'tipo_destinatario': 'tercero',
             'dependencia_id': None, 'tercero_id': uuid4(),
             'tipo_copia': 'principal',
             'fecha_lectura': None, 'leida_por_user_id': None},
        ]
        r = await svc.crear_externa_enviada_borrador(
            conn, tenant_id=uuid4(),
            dependencia_origen_id=uuid4(),
            asunto='X', contenido_borrador=None,
            prioridad='normal', documento_principal_id=None,
            plantilla_id=None,
            destinatarios=[{'tipo_destinatario': 'tercero',
                             'tercero_id': uuid4(),
                             'tipo_copia': 'principal'}],
            usuario_proyecta_id=uuid4(),
        )
        assert r['tipo'] == 'externa_enviada'
        assert r['estado'] == 'borrador'

    @pytest.mark.asyncio
    async def test_wf_enviar_revision_ok(self):
        conn = AsyncMock()
        cid = uuid4()
        conn.fetchrow.side_effect = [
            {'id': cid, 'tipo': 'externa_enviada', 'estado': 'borrador',
             'usuario_proyecta_id': uuid4()},
            _corresp_row(tipo='externa_enviada', estado='en_revision'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_enviar_a_revision(
            conn, tenant_id=uuid4(), correspondencia_id=cid,
            usuario_actor_id=uuid4(),
        )
        assert r['estado'] == 'en_revision'

    @pytest.mark.asyncio
    async def test_wf_enviar_revision_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.workflow_enviar_a_revision(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_wf_enviar_revision_tipo_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'interna', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError, match='tipo_invalido'):
            await svc.workflow_enviar_a_revision(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_enviar_revision_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada',
            'estado': 'aprobada', 'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError, match='estado_invalido'):
            await svc.workflow_enviar_a_revision(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_revisar_ok_aprueba(self):
        conn = AsyncMock()
        proyecta = uuid4()
        revisor = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'en_revision',
             'usuario_proyecta_id': proyecta},
            _corresp_row(tipo='externa_enviada', estado='aprobada'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_revisar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            resultado='ok', observaciones=None, usuario_actor_id=revisor,
        )
        assert r['estado'] == 'aprobada'

    @pytest.mark.asyncio
    async def test_wf_revisar_devuelve(self):
        conn = AsyncMock()
        proyecta = uuid4()
        revisor = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'en_revision',
             'usuario_proyecta_id': proyecta},
            _corresp_row(tipo='externa_enviada', estado='devuelta'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_revisar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            resultado='devolver', observaciones='corregir',
            usuario_actor_id=revisor,
        )
        assert r['estado'] == 'devuelta'

    @pytest.mark.asyncio
    async def test_wf_revisar_separacion(self):
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'en_revision',
            'usuario_proyecta_id': actor,
        }
        with pytest.raises(PermissionError):
            await svc.workflow_revisar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                resultado='ok', observaciones=None, usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_wf_revisar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.workflow_revisar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            resultado='ok', observaciones=None, usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_wf_revisar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.workflow_revisar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                resultado='ok', observaciones=None, usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_aprobar_ok(self):
        conn = AsyncMock()
        proyecta = uuid4()
        aprobador = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
             'usuario_proyecta_id': proyecta},
            _corresp_row(tipo='externa_enviada', estado='aprobada'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_aprobar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=aprobador,
        )
        assert r['estado'] == 'aprobada'

    @pytest.mark.asyncio
    async def test_wf_aprobar_separacion(self):
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
            'usuario_proyecta_id': actor,
        }
        with pytest.raises(PermissionError):
            await svc.workflow_aprobar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_wf_aprobar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.workflow_aprobar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_wf_aprobar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.workflow_aprobar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_firmar_ok(self):
        conn = AsyncMock()
        proyecta = uuid4()
        firmante = uuid4()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
             'usuario_proyecta_id': proyecta},
            _corresp_row(tipo='externa_enviada', estado='firmada'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_firmar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=firmante,
        )
        assert r['estado'] == 'firmada'

    @pytest.mark.asyncio
    async def test_wf_firmar_separacion(self):
        conn = AsyncMock()
        actor = uuid4()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'aprobada',
            'usuario_proyecta_id': actor,
        }
        with pytest.raises(PermissionError):
            await svc.workflow_firmar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=actor,
            )

    @pytest.mark.asyncio
    async def test_wf_firmar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.workflow_firmar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_wf_firmar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.workflow_firmar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_radicar_ok(self, monkeypatch):
        async def fake_sig(c, *, tenant_id, vigencia, tipo_radicado):
            return '2026-S-00010'
        monkeypatch.setattr(
            'app.gd.services.consecutivos.siguiente_radicado', fake_sig,
        )
        conn = AsyncMock()
        cid = uuid4()
        conn.fetchrow.side_effect = [
            {'tipo': 'externa_enviada', 'estado': 'firmada',
             'asunto': 'A', 'contenido_borrador': 'X',
             'dependencia_origen_id': uuid4(),
             'usuario_proyecta_id': uuid4()},
            {'id': uuid4(), 'numero_radicado': '2026-S-00010',
             'fecha_radicacion': datetime.now()},
            _corresp_row(tipo='externa_enviada', estado='radicada'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_radicar_salida(
            conn, tenant_id=uuid4(), correspondencia_id=cid,
            usuario_actor_id=uuid4(), canal_envio_id=uuid4(),
        )
        assert r['estado'] == 'radicada'

    @pytest.mark.asyncio
    async def test_wf_radicar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.workflow_radicar_salida(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_wf_radicar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'tipo': 'externa_enviada', 'estado': 'borrador',
            'asunto': 'A', 'contenido_borrador': None,
            'dependencia_origen_id': uuid4(),
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.workflow_radicar_salida(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_enviar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'radicada',
             'usuario_proyecta_id': uuid4()},
            _corresp_row(tipo='externa_enviada', estado='enviada'),
        ]
        conn.fetch.return_value = []
        r = await svc.workflow_enviar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(), canal_envio_id=uuid4(),
        )
        assert r['estado'] == 'enviada'

    @pytest.mark.asyncio
    async def test_wf_enviar_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.workflow_enviar(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_wf_enviar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.workflow_enviar(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            usuario_actor_id=uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_registrar_soporte_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'enviada',
             'usuario_proyecta_id': uuid4()},
            _corresp_row(tipo='externa_enviada', estado='enviada',
                          soporte_envio_uri='s3://x/y.pdf'),
        ]
        conn.fetch.return_value = []
        r = await svc.registrar_soporte_envio(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            soporte_envio_uri='s3://x/y.pdf',
            codigo_rastreo='ABC123', usuario_actor_id=uuid4(),
        )
        assert r['soporte_envio_uri'] == 's3://x/y.pdf'

    @pytest.mark.asyncio
    async def test_registrar_soporte_estado_invalido(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo': 'externa_enviada', 'estado': 'borrador',
            'usuario_proyecta_id': uuid4(),
        }
        with pytest.raises(ValueError):
            await svc.registrar_soporte_envio(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                soporte_envio_uri='s3://x', codigo_rastreo=None,
                usuario_actor_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_registrar_soporte_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.registrar_soporte_envio(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            soporte_envio_uri='x', codigo_rastreo=None,
            usuario_actor_id=uuid4(),
        ) is None


# =============================================================================
# Anulación (GD-API-0056)
# =============================================================================
class TestAnulacion:
    @pytest.mark.asyncio
    async def test_solicitar_ok(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'enviada'
        conn.fetchrow.return_value = {
            'id': uuid4(), 'tipo_entidad': 'correspondencia',
            'entidad_afectada_id': uuid4(), 'solicitante_user_id': uuid4(),
            'motivo': 'duplicado', 'decision': 'pendiente',
            'aprobador_user_id': None, 'observacion_decision': None,
            'fecha_solicitud': datetime.now(), 'fecha_decision': None,
        }
        r = await svc.solicitar_anulacion(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            motivo='duplicado de envío', evidencia_archivo_digital_id=None,
            solicitante_user_id=uuid4(),
        )
        assert r['decision'] == 'pendiente'

    @pytest.mark.asyncio
    async def test_solicitar_ya_anulada(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 'anulada'
        with pytest.raises(ValueError, match='ya_anulada'):
            await svc.solicitar_anulacion(
                conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
                motivo='x' * 10, evidencia_archivo_digital_id=None,
                solicitante_user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_solicitar_not_found(self):
        conn = AsyncMock()
        conn.fetchval.return_value = None
        r = await svc.solicitar_anulacion(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
            motivo='x', evidencia_archivo_digital_id=None,
            solicitante_user_id=uuid4(),
        )
        assert r is None

    @pytest.mark.asyncio
    async def test_aprobar_ok(self):
        conn = AsyncMock()
        corresp_id = uuid4()
        conn.fetchrow.side_effect = [
            {'entidad_afectada_id': corresp_id, 'decision': 'pendiente'},
            {'id': uuid4(), 'tipo_entidad': 'correspondencia',
             'entidad_afectada_id': corresp_id, 'solicitante_user_id': uuid4(),
             'motivo': 'X', 'decision': 'aprobada',
             'aprobador_user_id': uuid4(),
             'observacion_decision': 'ok', 'fecha_solicitud': datetime.now(),
             'fecha_decision': datetime.now()},
        ]
        r = await svc.aprobar_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(), observacion='ok',
        )
        assert r['decision'] == 'aprobada'

    @pytest.mark.asyncio
    async def test_aprobar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.aprobar_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(), observacion=None,
        ) is None

    @pytest.mark.asyncio
    async def test_aprobar_ya_decidida(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            'entidad_afectada_id': uuid4(), 'decision': 'aprobada',
        }
        with pytest.raises(ValueError, match='solicitud_ya_decidida'):
            await svc.aprobar_anulacion(
                conn, tenant_id=uuid4(), solicitud_id=uuid4(),
                aprobador_user_id=uuid4(), observacion=None,
            )

    @pytest.mark.asyncio
    async def test_rechazar_ok(self):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [
            {'decision': 'pendiente'},
            {'id': uuid4(), 'tipo_entidad': 'correspondencia',
             'entidad_afectada_id': uuid4(), 'solicitante_user_id': uuid4(),
             'motivo': 'X', 'decision': 'rechazada',
             'aprobador_user_id': uuid4(), 'observacion_decision': 'no',
             'fecha_solicitud': datetime.now(), 'fecha_decision': datetime.now()},
        ]
        r = await svc.rechazar_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(), observacion='no procede',
        )
        assert r['decision'] == 'rechazada'

    @pytest.mark.asyncio
    async def test_rechazar_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        assert await svc.rechazar_anulacion(
            conn, tenant_id=uuid4(), solicitud_id=uuid4(),
            aprobador_user_id=uuid4(), observacion='no',
        ) is None

    @pytest.mark.asyncio
    async def test_rechazar_ya_decidida(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = {'decision': 'aprobada'}
        with pytest.raises(ValueError, match='solicitud_ya_decidida'):
            await svc.rechazar_anulacion(
                conn, tenant_id=uuid4(), solicitud_id=uuid4(),
                aprobador_user_id=uuid4(), observacion='no',
            )


# =============================================================================
# Listado + obtener
# =============================================================================
class TestListado:
    @pytest.mark.asyncio
    async def test_listar_sin_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_correspondencia(conn, tenant_id=uuid4())
        assert r == []

    @pytest.mark.asyncio
    async def test_listar_con_todos_filtros(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        r = await svc.listar_correspondencia(
            conn, tenant_id=uuid4(), tipo='interna',
            estado=['enviada', 'leida'],
            dependencia_id=uuid4(), tercero_id=uuid4(), limit=10,
        )
        assert r == []

    @pytest.mark.asyncio
    async def test_contar_sin_filtro(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 42
        assert await svc.contar_correspondencia(conn, tenant_id=uuid4()) == 42

    @pytest.mark.asyncio
    async def test_contar_con_tipo(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 10
        assert await svc.contar_correspondencia(
            conn, tenant_id=uuid4(), tipo='externa_recibida',
        ) == 10

    @pytest.mark.asyncio
    async def test_obtener_ok(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = _corresp_row(tipo='interna', estado='enviada')
        conn.fetch.return_value = []
        r = await svc.obtener_correspondencia(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
        )
        assert r is not None
        assert r['destinatarios'] == []

    @pytest.mark.asyncio
    async def test_obtener_not_found(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        r = await svc.obtener_correspondencia(
            conn, tenant_id=uuid4(), correspondencia_id=uuid4(),
        )
        assert r is None
