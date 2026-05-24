"""Tests estáticos para `app.gd.services.audit_emitter` (GD-API-0117).

Cubre validaciones que no requieren DB real:
- Validación de enum `AuditCriticidad`.
- Validación de enum `AuditDominio`.
- Rechazo de valores inválidos antes de tocar DB.
- Serialización jsonb correcta.

Tests de integración (insert real) están en test_gd_audit_emitter_integration.py
(corre solo con `RUN_INTEGRATION=1` + docker postgres up).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.gd.services.audit_emitter import (
    AuditCriticidad,
    AuditDominio,
    emit_audit_event,
    emit_gd_event,
)


class TestEnums:
    """Los enums son la fuente de verdad — deben coincidir con el CHECK SQL."""

    def test_criticidad_values_match_sql_check(self) -> None:
        """SQL define: check (criticidad in ('baja', 'media', 'alta', 'critica'))."""
        expected = {'baja', 'media', 'alta', 'critica'}
        actual = {c.value for c in AuditCriticidad}
        assert actual == expected, (
            f'Enum AuditCriticidad desfasado de infra/postgres/04-gd-schema.sql. '
            f'Esperado: {expected}, encontrado: {actual}.'
        )

    def test_dominio_values_match_sql_check(self) -> None:
        """SQL define: check (dominio in ('core', 'app', 'gd', 'knowledge'))."""
        expected = {'core', 'app', 'gd', 'knowledge'}
        actual = {d.value for d in AuditDominio}
        assert actual == expected, (
            f'Enum AuditDominio desfasado de infra/postgres/04-gd-schema.sql. '
            f'Esperado: {expected}, encontrado: {actual}.'
        )


class TestEmitAuditEventValidation:
    """`emit_audit_event` debe rechazar inputs inválidos ANTES de tocar la DB."""

    @pytest.mark.asyncio
    async def test_rechaza_criticidad_invalida(self) -> None:
        conn = AsyncMock()
        with pytest.raises(ValueError, match='criticidad inválida'):
            await emit_audit_event(
                conn,
                dominio='gd',
                tipo_evento='test',
                accion='test',
                criticidad='inexistente',  # type: ignore[arg-type]
            )
        # Crítico: si la validación falla DESPUÉS de tocar DB, hay leak.
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_rechaza_dominio_invalido(self) -> None:
        conn = AsyncMock()
        with pytest.raises(ValueError, match='dominio inválido'):
            await emit_audit_event(
                conn,
                dominio='inexistente',
                tipo_evento='test',
                accion='test',
            )
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_acepta_criticidad_enum(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4()}
        # No debe lanzar.
        await emit_audit_event(
            conn,
            dominio='gd',
            tipo_evento='test',
            accion='test',
            criticidad=AuditCriticidad.ALTA,
        )
        conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acepta_criticidad_string_valido(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4()}
        await emit_audit_event(
            conn,
            dominio='gd',
            tipo_evento='test',
            accion='test',
            criticidad='critica',
        )
        conn.fetchrow.assert_awaited_once()


class TestEmitAuditEventSqlCall:
    """Verifica que el SQL invocado mantiene el orden de parámetros esperado."""

    @pytest.mark.asyncio
    async def test_pasa_actor_snapshot_como_jsonb(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4()}
        snapshot = {'nombre': 'Juan', 'rol': 'gd.profesional'}
        await emit_audit_event(
            conn,
            dominio='gd',
            tipo_evento='gd.test',
            accion='crear',
            actor_snapshot=snapshot,
        )
        args = conn.fetchrow.call_args.args
        # SQL es args[0]; actor_snapshot debe ser arg index 6 según el call.
        # Validamos que es un string JSON parseable y que coincide.
        actor_arg = args[6]
        assert isinstance(actor_arg, str)
        assert json.loads(actor_arg) == snapshot

    @pytest.mark.asyncio
    async def test_valor_anterior_y_nuevo_se_serializan_solo_si_no_none(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4()}
        await emit_audit_event(
            conn,
            dominio='gd',
            tipo_evento='gd.test',
            accion='crear',
            valor_anterior=None,
            valor_nuevo={'campo': 'valor'},
        )
        args = conn.fetchrow.call_args.args
        # valor_anterior es index 10, valor_nuevo es index 11
        assert args[10] is None
        assert isinstance(args[11], str)
        assert json.loads(args[11]) == {'campo': 'valor'}


class TestEmitGdEventShortcut:
    """`emit_gd_event` debe forzar dominio='gd'."""

    @pytest.mark.asyncio
    async def test_emit_gd_event_fija_dominio_gd(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': uuid4()}
        tenant = uuid4()
        await emit_gd_event(
            conn,
            tipo_evento='gd.radicado.creado',
            accion='crear',
            tenant_id=tenant,
        )
        args = conn.fetchrow.call_args.args
        # dominio es el primer parámetro (args[1] porque args[0] es el SQL string)
        assert args[1] == 'gd'
