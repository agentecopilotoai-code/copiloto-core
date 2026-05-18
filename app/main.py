from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.v1.routes import router as v1_router
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.pool import db
from app.services.metrics import (
    ip_allowed,
    parse_ip_allowlist,
    refresh_backup_age_metrics,
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
    api.middleware('http')(build_rate_limit_middleware(limiter))

    api.include_router(admin_router)
    api.include_router(v1_router)
    return api


app = create_app()
