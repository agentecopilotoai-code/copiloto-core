from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.v1.routes import router as v1_router
from app.admin.routes import router as admin_router
from app.core.config import get_settings
# Branch `core`: el core NO incluye módulos opt-in. Cada módulo se monta
# como add-on por separado al instalarse sobre el core (ver
# `docs/ARCHITECTURE.md` § "Cómo agregar un módulo nuevo").
#
# Endpoints platform admin transversales (`/v1/platform/ai-providers/*`,
# `/v1/platform/tenant-modules/*`) viven en `app/platform_admin/admin_routes.py`
# y se cargan por side-effect desde `app/api/v1/routes.py`.
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
    from app.services.http_clients import close_all as _close_http_clients  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.log_level)
    await db.connect(settings.database_url)
    try:
        yield
    finally:
        await db.close()
        # PERF-001 (audit 2026-05-27) — cerrar todos los httpx clients
        # singleton para liberar sockets limpiamente. Llamado en `finally`
        # para no leakear conexiones si la app falla durante el run.
        await _close_http_clients()


def _client_ip(request: Request) -> str | None:
    """IP del cliente. Ignora X-Forwarded-For: el endpoint se restringe por red
    privada y un proxy mal configurado no debe degradar la allowlist."""
    if request.client is None:
        return None
    return request.client.host


_SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'interest-cohort=(), browsing-topics=()',
    # HSTS solo aplica detrás de HTTPS — al levantar local en http es benigno
    # (el browser lo ignora). En prod detrás de TLS, fuerza HTTPS-only por 1 año.
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    # CSP defensiva: solo cargamos assets locales, no inline scripts (Vite
    # genera bundles externos). Si un módulo opt-in requiere CDN específico,
    # lo extiende vía middleware adicional.
    'Content-Security-Policy': (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self' https://*.auth0.com"
    ),
}


async def _security_headers_middleware(request: Request, call_next):
    """Adjunta security headers a CADA response.

    `Content-Security-Policy`, `X-Frame-Options`, etc. defienden contra:
      - clickjacking (X-Frame-Options DENY)
      - MIME sniffing (X-Content-Type-Options nosniff)
      - referrer leak (Referrer-Policy no-referrer)
      - downgrade HTTP (HSTS)
      - cross-site script/asset injection (CSP)
    """
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)
    allowlist = parse_ip_allowlist(settings.observability_allowed_ips)

    @api.get('/metrics', include_in_schema=False)
    async def metrics(request: Request) -> Response:
        if not ip_allowed(_client_ip(request), allowlist):
            return Response(status_code=403)
        try:
            async with db.connection() as conn:
                await refresh_backup_age_metrics(conn)
        except Exception:  # noqa: BLE001
            pass
        refresh_runtime_metrics()
        payload, content_type = render_latest()
        return Response(content=payload, media_type=content_type)

    # Security headers — registrar antes que el rate limiter para que TODAS
    # las responses (incluso 429) los lleven.
    api.middleware('http')(_security_headers_middleware)

    # Rate limiting runs first (outermost). Starlette wraps middlewares in
    # reverse order of registration, so this must be added last.
    limiter = RateLimiter(
        default_per_minute=settings.rate_limit_per_min,
        webhook_per_minute=settings.rate_limit_webhook_per_min,
        max_entries=settings.rate_limit_bucket_max_entries,
        ttl_seconds=settings.rate_limit_bucket_ttl_seconds,
    )
    # Registrar el limiter para que `refresh_runtime_metrics`
    # pueda leer `.size` sin import circular.
    _set_active_rate_limiter(limiter)
    api.middleware('http')(build_rate_limit_middleware(limiter))

    api.include_router(admin_router)
    api.include_router(v1_router)
    # Branch `core`: ningún router de producto se monta. Los módulos opt-in
    # registran sus routers cuando se instalan sobre el core, agregando sus
    # propios `api.include_router(...)` acá o vía un hook de carga dinámica
    # (TODO Fase 3 — module discovery con manifest.json).
    return api


app = create_app()
