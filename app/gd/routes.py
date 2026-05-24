"""Router principal del módulo Gestión Documental.

Monta todos los sub-routers del módulo bajo el prefijo `/api/v1/gd`. Se registra
desde `app/main.py` (no desde `app/api/v1/routes.py` para no inflar más esa
megalítica de 1700+ líneas).

Convención: cada épica tiene su(s) handler(s) en `app/gd/handlers/`, los importa
y agrega aquí. Ejemplos:
    - me_handlers.router    → endpoints de identidad del usuario actual
    - perfil_handlers.router (futuro)
    - roles_handlers.router  (futuro)
    - radicado_handlers.router (futuro EP-004)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.gd import ensure_gd_module_enabled
from app.gd.handlers import (
    alertas_handlers,
    archivos_handlers,
    asignaciones_handlers,
    catalogos_handlers,
    consecutivos_handlers,
    contactos_handlers,
    correo_handlers,
    correspondencia_handlers,
    dependencias_handlers,
    documentos_handlers,
    expedientes_handlers,
    firmas_handlers,
    ia_handlers,
    me_handlers,
    notificaciones_handlers,
    organizacion_handlers,
    parametros_handlers,
    perfil_usuario_handlers,
    perifericos_handlers,
    perifericos2_handlers,
    plantillas_handlers,
    politica_contrasena_handlers,
    pqrsd_handlers,
    radicados_handlers,
    reportes_handlers,
    rpa_handlers,
    roles_handlers,
    tareas_buzon_handlers,
    tareas_handlers,
    terceros_handlers,
    trd_handlers,
    utilidades_handlers,
)


# El router raíz del módulo. Se monta en main.py con prefix='/api/v1/gd'.
router = APIRouter(prefix='/api/v1/gd', tags=['gd'])


# ─── Health-check del módulo ───────────────────────────────────────────────
# Endpoint mínimo gateado por `ensure_gd_module_enabled`: si responde 200
# significa que el tenant tiene `tenant_modules.gestion_documental.enabled=true`
# y la auth funcionó. Si responde 404, el módulo no está activo para el
# tenant (D2 — 404 en lugar de 403 para no filtrar la existencia del feature).
@router.get(
    '/_health',
    summary='Internal: verifica que el módulo GD está activo para el tenant',
    dependencies=[Depends(ensure_gd_module_enabled)],
)
async def gd_module_health() -> dict[str, str]:
    """Si llega aquí, el tenant tiene el módulo activo."""
    return {'module': 'gestion_documental', 'status': 'active'}


# Alias del health-check accesible via el BFF (`admin_core_api_proxy`). El
# BFF strippea `/admin/api/core/` y forwardea a upstream — por eso necesita
# el endpoint disponible en `/v1/gd/_health` (sin el prefijo `/api`). Sin
# este alias, el frontend `isGdEnabled` (en `services/coreApi.js`) recibe
# 404 incluso cuando el tenant SÍ tiene el módulo activo, y el item del
# sidebar nunca aparece. Mismo patrón que `/v1/influencer/_health`.
router_health_alias = APIRouter(prefix='/v1/gd', tags=['gd'])


@router_health_alias.get(
    '/_health',
    summary='Internal: verifica que el módulo GD está activo para el tenant (BFF alias)',
    dependencies=[Depends(ensure_gd_module_enabled)],
)
async def gd_module_health_alias() -> dict[str, str]:
    """Idéntico a `/api/v1/gd/_health` — alias para el BFF admin."""
    return {'module': 'gestion_documental', 'status': 'active'}

# Router transversal /api/v1/core/* — servicios compartidos con Knowledge.
# Se monta en main.py separado de `router`. EP-018 archivos vive aquí.
router_core = APIRouter(prefix='/api/v1/core', tags=['core'])
router_core.include_router(archivos_handlers.router)
# GD-API-0119/0120: auditoría consulta + catálogo.
router_core.include_router(utilidades_handlers.router_audit)

# Router público SIN /api/v1 — solo para verificación de constancia QR.
# Se monta en main.py al root level.
router_public = APIRouter(tags=['publica'])
router_public.include_router(utilidades_handlers.router_constancia_pub)

# Sub-routers por dominio:
router.include_router(me_handlers.router)
router.include_router(perfil_usuario_handlers.router)
router.include_router(roles_handlers.router)
router.include_router(asignaciones_handlers.router)
router.include_router(politica_contrasena_handlers.router)
# tareas_handlers comparte prefix /perfil-usuario con perfil_usuario_handlers;
# las rutas son específicas (/{user_id}/tareas-pendientes y /{user_id}/tareas/reasignar)
# y no chocan con las de perfil_usuario_handlers.
router.include_router(tareas_handlers.router)
# GD-API-0011: /api/v1/gd/organizacion + /api/v1/gd/organizacion/modulos
router.include_router(organizacion_handlers.router)
# GD-API-0012: /api/v1/gd/dependencias + /api/v1/gd/estructura/*
router.include_router(dependencias_handlers.router_dependencias)
router.include_router(dependencias_handlers.router_estructura)
# GD-API-0013, 0014, 0016: catálogos institucionales
router.include_router(catalogos_handlers.router_cargos)
router.include_router(catalogos_handlers.router_canales)
router.include_router(catalogos_handlers.router_calendarios)
router.include_router(catalogos_handlers.router_tipos_pqrsd)
router.include_router(catalogos_handlers.router_tipos_corresp)
router.include_router(catalogos_handlers.router_reglas)
# GD-API-0015: parámetros institucionales versionados
router.include_router(parametros_handlers.router)
# GD-API-0023: consecutivos transaccionales radicación
router.include_router(consecutivos_handlers.router)
# GD-API-0033: terceros (CRUD + búsqueda con detección duplicados)
router.include_router(terceros_handlers.router)
# GD-API-0024..0029: Ventanilla Única — radicados + clasificación + anulación
router.include_router(radicados_handlers.router_ventanilla)
# GD-API-0034 + GD-API-0035: contactos del tercero + historial
router.include_router(contactos_handlers.router)
# GD-API-0036..0039: tareas + buzón
router.include_router(tareas_buzon_handlers.router_tareas)
router.include_router(tareas_buzon_handlers.router_buzon)
# GD-API-0040: notificaciones + preferencias
router.include_router(notificaciones_handlers.router_notif)
router.include_router(notificaciones_handlers.router_pref)
# GD-API-0041: alertas críticas
router.include_router(alertas_handlers.router)
# GD-API-0042..0046: PQRSD (asignación + reasignación + respuestas + suspensión)
# GD-API-0047..0051: bloque 8 — workflow respuesta + cierre + traslado + dashboard
# IMPORTANTE: router_dashboard se monta ANTES de router para que /pqrsd/dashboard
# no choque con /pqrsd/{pqrsd_id}.
router.include_router(pqrsd_handlers.router_dashboard)
router.include_router(pqrsd_handlers.router)
router.include_router(pqrsd_handlers.router_respuestas)
# GD-API-0052..0056: correspondencia interna + externa + anulación
router.include_router(correspondencia_handlers.router)
# GD-API-0057..0063: documentos + versiones + anexos + descarga auditada
router.include_router(documentos_handlers.router_docs)
router.include_router(documentos_handlers.router_anexos)
router.include_router(documentos_handlers.router_archivos)
# GD-API-0064..0067: plantillas documentales
# admin (con prefijo _seed) DEBE ir antes que router principal para que
# /_seed-institucionales no colisione con /{plantilla_id}.
router.include_router(plantillas_handlers.router_admin)
router.include_router(plantillas_handlers.router)
# GD-API-0068..0072: firmas (escaneada + electrónica + digital + evidencia)
router.include_router(firmas_handlers.router_firmas_esc)
router.include_router(firmas_handlers.router_docs_firma)
router.include_router(firmas_handlers.router_firmas)
# GD-API-0073..0076: correo institucional (buzones + correos importados)
router.include_router(correo_handlers.router)
# GD-API-0077..0086: agentes IA asistidos (sugerencias + decisión humana)
router.include_router(ia_handlers.router)
# GD-API-0087..0094: reportes e indicadores + exportación auditada
router.include_router(reportes_handlers.router)
# GD-API-0095..0100: TRD/TVD + clasificación documental
router.include_router(trd_handlers.router_trd)
router.include_router(trd_handlers.router_tvd)
router.include_router(trd_handlers.router_dep)
router.include_router(trd_handlers.router_clasif)
# GD-API-0101..0104: expediente electrónico básico
router.include_router(expedientes_handlers.router)
# GD-API-0105..0109: RPA + APIs públicas + webhooks + rate limit
router.include_router(rpa_handlers.router_ident)
router.include_router(rpa_handlers.router_rpa)
router.include_router(rpa_handlers.router_wh)
router.include_router(rpa_handlers.router_rl)
# GD-API-0122..0126: utilidades EP-020 (constancia priv + tipos doc id +
# cambios deps + contingencia + hoja control).
router.include_router(utilidades_handlers.router_constancia_priv)
router.include_router(utilidades_handlers.router_tipos)
router.include_router(utilidades_handlers.router_org_tipos)
router.include_router(utilidades_handlers.router_estructura)
router.include_router(utilidades_handlers.router_contingencia)
router.include_router(utilidades_handlers.router_hoja)
# GD-API-0128..0135: EP-021 periféricos parte 1 (puntos atención, periféricos,
# códigos barras/QR, impresión etiqueta/constancia, reimpresión,
# digitalización individual). Gate por módulo `ventanilla_presencial_con_
# perifericos` activo en cada handler (404 si no).
router.include_router(perifericos_handlers.router_puntos)
# GD-API-0136..0142: EP-021 periféricos parte 2 — CIERRE backlog.
# D76: `router_perif_literals` monta `/perifericos/{literal}` (lotes,
# contexto-activo, eventos/fallos, historial-uso-global, historial/exportar)
# y DEBE registrarse ANTES de `router_perif` del bloque 21a para que el
# validator UUID de `/{periferico_id}` no devuelva 422 al recibir un
# segmento literal. Mismo patrón que pqrsd/dashboard vs pqrsd/{id} (D16).
router.include_router(perifericos2_handlers.router_perif_literals)
router.include_router(perifericos_handlers.router_perif)
router.include_router(perifericos_handlers.router_codigos)
# `router_perif_b` solo agrupa rutas con `/{periferico_id}/...` (no
# colisiona con literales una vez separadas arriba).
router.include_router(perifericos2_handlers.router_perif_b)
router.include_router(perifericos2_handlers.router_agentes)
router.include_router(perifericos2_handlers.router_digit)


__all__ = ['router', 'router_core', 'router_public']
