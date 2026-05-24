"""Test específico para cubrir el branch de fallo de auditoría en require_gd_permission.

Cuando `emit_gd_event` falla (ej. DB temporalmente caída), la denegación 403
NO debe bloquearse — el except logguea y sigue.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.gd.security import GdPerfilContext, require_gd_permission


@pytest.mark.asyncio
async def test_audit_failure_no_bloquea_403(monkeypatch):
    """Si emit_gd_event lanza, igual recibimos 403 (no 500)."""
    check = require_gd_permission('PERM-X', alcance='global')

    perfil = GdPerfilContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        perfil_id=uuid4(),
        tipo_vinculacion='planta',
        estado_gd='activo',
        dependencia_actual_id=None,
        cargo_actual_id=None,
    )
    conn = AsyncMock()
    conn.fetch.return_value = []  # sin permisos → 403

    async def _emit_fail(*args, **kwargs):
        raise RuntimeError('DB momentáneamente inaccesible')

    monkeypatch.setattr(
        'app.gd.services.audit_emitter.emit_gd_event', _emit_fail
    )

    request = MagicMock()
    request.state.request_id = 'req_test'

    with pytest.raises(HTTPException) as exc:
        await check(request, perfil, conn)
    assert exc.value.status_code == 403
