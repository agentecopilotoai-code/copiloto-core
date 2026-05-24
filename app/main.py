from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.v1.routes import router as v1_router
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.influencer.router import influencer_router
from app.influencer.personas_router import personas_router as influencer_personas_router
from app.influencer.wizard_router import wizard_router as influencer_wizard_router
from app.influencer.face_variations_router import (
    face_variations_router as influencer_face_variations_router,
    storage_router as influencer_storage_router,
)
from app.influencer.generations_router import (
    generate_router as influencer_generate_router,
    generations_router as influencer_generations_router,
)
from app.influencer.voice_router import voice_router as influencer_voice_router
from app.influencer.instagram_router import instagram_router as influencer_instagram_router
from app.influencer.posts_router import posts_router as influencer_posts_router
from app.influencer.credits_router import (
    credits_router as influencer_credits_router,
    pricing_router as influencer_pricing_router,
)
from app.influencer.casting_router import casting_router as influencer_casting_router
# GD-API-0002 — Módulo Gestión Documental. Router raíz que monta sub-routers
# por épica (identidad, ventanilla, pqrsd, etc.). El gate de visibilidad de
# rutas se hace dentro de cada handler vía `require_gd_perfil` (devuelve 403
# con code='gd_profile_missing_or_inactive' para usuarios sin perfil GD activo
# en el tenant). El router siempre se monta; tenants sin GD simplemente
# reciben 403 — análogo al patrón del módulo influencer.
from app.gd.routes import (
    router as gd_router,
    router_core as gd_router_core,
    router_public as gd_router_public,
    router_health_alias as gd_router_health_alias,
)
# NOTA — el import side-effect que registra los endpoints
# `/v1/platform/ai-providers*` y `/v1/platform/tenant-modules*` sobre
# `platform_admin_router` (TASK-INFLU-002 + TASK-INFLU-019) ya se ejecuta
# desde dentro de `app/api/v1/routes.py` antes del `router.include_router(
# platform_admin_router)` final. Importarlo aquí ahora es redundante y
# además es tardío (FastAPI ya copió las rutas en el include_router).
# Ver el comentario en `app/api/v1/routes.py:1695` para el detalle.
from app.core.logging import configure_logging
from app.db.pool import db
from app.services.metrics import (
    _set_active_rate_limiter,
    ip_allowed,
    parse_ip_allowlist,
    refresh_backup_age_metrics,
    refresh_runtime_metrics,
    render_latest,
)
from app.services.rate_limit import (
    RateLimiter,
    build_rate_limit_middleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await db.connect(settings.database_url)
    yield
    await db.close()


def _is_web_widget_path(path: str) -> bool:
    return path.startswith('/v1/web/')


def _client_ip(request: Request) -> str | None:
    """IP del cliente. Ignora X-Forwarded-For: el endpoint se restringe por red
    privada y un proxy mal configurado no debe degradar la allowlist."""
    if request.client is None:
        return None
    return request.client.host


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)
    allowlist = parse_ip_allowlist(settings.observability_allowed_ips)

    @api.get('/metrics', include_in_schema=False)
    async def metrics(request: Request) -> Response:
        if not ip_allowed(_client_ip(request), allowlist):
            return Response(status_code=403)
        # BUG-047: refrescar gauges de backup desde `app.backup_runs` ANTES
        # de serializar. Sin esto, los gauges quedaban vacíos y las reglas
        # `BackupCloudStale` / `BackupVerifyFailed` (alerts.yaml) nunca
        # paginaban — backups stale silentes. `app.backup_runs` es platform-
        # scoped (sin RLS), así que `db.connection()` sin tenant alcanza.
        # Best-effort: si la pool no está lista o la DB cae, el helper
        # loguea y el endpoint sirve los valores en memoria (sin crashear).
        try:
            async with db.connection() as conn:
                await refresh_backup_age_metrics(conn)
        except Exception:  # noqa: BLE001
            # No bloquear /metrics si la DB se cae — scrape sigue sirviendo
            # el resto de las métricas. La alerta `PostgresUnavailable` (si
            # se llega a configurar) cubrirá la caída de DB independientemente.
            pass
        # AUDIT-51: refrescar gauges runtime (fanout + rate-limit) sin tocar DB.
        refresh_runtime_metrics()
        payload, content_type = render_latest()
        return Response(content=payload, media_type=content_type)


    @api.middleware('http')
    async def web_widget_cors(request: Request, call_next):
        """Add permissive CORS headers for the public web-widget endpoints.

        The widget is embedded on third-party sites; per-tenant origin
        validation happens inside the endpoint using ``allowed_origins``.
        Here we only need to satisfy the browser preflight so the request
        reaches FastAPI.
        """
        if not _is_web_widget_path(request.url.path):
            return await call_next(request)
        origin = request.headers.get('origin', '*')
        if request.method == 'OPTIONS':
            response = Response(status_code=204)
        else:
            response = await call_next(request)
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        response.headers['Access-Control-Max-Age'] = '600'
        return response

    # Rate limiting runs first (outermost). Starlette wraps middlewares in
    # reverse order of registration, so this must be added last.
    limiter = RateLimiter(
        default_per_minute=settings.rate_limit_per_min,
        webhook_per_minute=settings.rate_limit_webhook_per_min,
        max_entries=settings.rate_limit_bucket_max_entries,
        ttl_seconds=settings.rate_limit_bucket_ttl_seconds,
    )
    # AUDIT-51: registrar el limiter para que `refresh_runtime_metrics`
    # pueda leer `.size` sin import circular.
    _set_active_rate_limiter(limiter)
    api.middleware('http')(build_rate_limit_middleware(limiter))

    api.include_router(admin_router)
    api.include_router(v1_router)
    # TASK-INFLU-001 — módulo opcional Ravit Studio. El router siempre se
    # monta; el gate `ensure_module_enabled` en cada endpoint responde 404
    # cuando el tenant no tiene la fila `app.tenant_modules.influencer
    # enabled=true`. No filtramos la existencia del módulo a tenants sin
    # acceso (decisión D2 del backlog).
    api.include_router(influencer_router)
    # TASK-INFLU-008 — CRUD de personajes. Sub-router montado al lado del
    # router principal (`/v1/influencer/_health` vs
    # `/v1/influencer/personas/*`) para mantener flat el árbol de rutas
    # del módulo. Comparte las dependencies `authenticate_request` +
    # `ensure_module_enabled` configuradas en cada sub-router.
    api.include_router(influencer_personas_router)
    # TASK-INFLU-009 — wizard endpoints (PUT /face /body /identity /voice
    # /platforms + POST /activate) bajo el mismo prefix de personas.
    api.include_router(influencer_wizard_router)
    # TASK-INFLU-010 — face variations async (POST encola, GET status).
    api.include_router(influencer_face_variations_router)
    # UI-INFLU-014.7 — GET /v1/influencer/storage/{key:path} sirve los
    # archivos del storage del tenant (local Docker volume o S3) con
    # auth + tenant_scope.
    api.include_router(influencer_storage_router)
    # TASK-INFLU-011 — generaciones genéricas + lookup de assets.
    api.include_router(influencer_generate_router)
    api.include_router(influencer_generations_router)
    # TASK-INFLU-013 — voice sample + captions preview.
    api.include_router(influencer_voice_router)
    # TASK-INFLU-014 — Instagram OAuth (primer plataforma).
    api.include_router(influencer_instagram_router)
    # TASK-INFLU-015 — posts + calendar + publish queue.
    api.include_router(influencer_posts_router)
    # TASK-INFLU-016 — credit ledger + pricing.
    api.include_router(influencer_credits_router)
    api.include_router(influencer_pricing_router)
    # TASK-INFLU-017 — casting home + studio detail.
    api.include_router(influencer_casting_router)
    # GD-API-0002 — Módulo Gestión Documental. Monta /api/v1/gd/* con sus
    # sub-routers por épica. Los handlers usan require_gd_perfil para gating;
    # tenants sin perfil GD activo reciben 403 con code claro.
    api.include_router(gd_router)
    # GD-WIRE-01 — alias `/v1/gd/_health` accesible vía el BFF
    # `admin_core_api_proxy` (que strippea `/admin/api/core/` y forwardea
    # a upstream sin el prefijo `/api`). Sin este alias, el frontend
    # `isGdEnabled` recibe 404 y el item "Gestión Documental" no aparece
    # en el sidebar del tenant. Mismo patrón que `/v1/influencer/_health`.
    api.include_router(gd_router_health_alias)
    # EP-018 — servicio transversal /api/v1/core/* (archivos compartido).
    api.include_router(gd_router_core)
    # GD-API-0122 — endpoint público SIN auth para verificación QR
    # constancia. Vive en /gd/verificar/{codigo}, NO bajo /api/v1.
    api.include_router(gd_router_public)
    return api


app = create_app()
