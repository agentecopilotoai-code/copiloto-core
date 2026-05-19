"""Influencer module router — TASK-INFLU-001 skeleton.

Este router monta todos los endpoints del módulo Ravit Studio bajo el prefix
``/v1/influencer/*``. Cada endpoint hereda automáticamente el gate
``ensure_module_enabled`` (404 si el tenant no tiene el módulo activo) más
``authenticate_request`` para autenticación estándar.

Endpoints concretos vienen en las siguientes TASK-INFLU-*:
    - TASK-INFLU-008: personas CRUD.
    - TASK-INFLU-009: wizard 5 pasos.
    - TASK-INFLU-010: variaciones de cara.
    - TASK-INFLU-011/012: generación de contenido.
    - TASK-INFLU-013: voz / TTS.
    - TASK-INFLU-014/015: plataformas + posts/publish.
    - TASK-INFLU-016: créditos.
    - TASK-INFLU-017: casting / studio (read).

Este archivo entrega solo el skeleton + un endpoint de health interno que
permite validar que el gate funciona contra una DB real desde tests E2E.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import authenticate_request
from app.influencer import ensure_module_enabled

# Prefix dedicado al módulo. NO usamos sub-routers internos en esta tarea
# — cada TASK-INFLU-* posterior va a hacer ``influencer_router.include_router``
# de su sub-router. Mantener flat el árbol simplifica el montaje.
influencer_router = APIRouter(
    prefix='/v1/influencer',
    tags=['influencer'],
    dependencies=[
        # Auth viene primero (poblar request.state.tenant_id/roles/etc.),
        # luego el gate del módulo que lee tenant_id y consulta
        # ``app.tenant_modules``. Si el módulo no está activo, 404 ANTES
        # de entrar a la lógica del endpoint.
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


@influencer_router.get(
    '/_health',
    summary='Internal: verifica que el módulo está activo para el tenant',
    response_model=None,
)
async def influencer_module_health() -> dict[str, str]:
    """Health check del módulo, gateado por ``ensure_module_enabled``.

    Es el endpoint mínimo del skeleton: si llega aquí significa que
    el tenant tiene el módulo activo y la auth + el gate funcionaron.
    Lo usan los tests E2E para validar el camino feliz / no-feliz.

    Returns:
        ``{"module": "influencer", "status": "active"}``.
    """
    return {'module': 'influencer', 'status': 'active'}


__all__ = ['influencer_router']
