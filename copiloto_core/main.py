from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from copiloto_core.api.v1.routes import router as v1_router
from copiloto_core.admin.routes import router as admin_router
from copiloto_core.core.config import get_settings
from copiloto_core.extension import CoreModule
# Branch `core`: el core NO incluye módulos opt-in. Cada módulo se monta
# como add-on por separado al instalarse sobre el core (ver
# `ARCHITECTURE.md` § "Cómo agregar un módulo opt-in").
#
# Endpoints platform admin transversales (`/v1/platform/ai-providers/*`,
# `/v1/platform/tenant-modules/*`) viven en `app/platform_admin/admin_routes.py`
# y se cargan por side-effect desde `app/api/v1/routes.py`.
from copiloto_core.core.logging import configure_logging
from copiloto_core.db.pool import db
from copiloto_core.services.metrics import (
    _set_active_rate_limiter,
    ip_allowed,
    parse_ip_allowlist,
    refresh_backup_age_metrics,
    refresh_runtime_metrics,
    render_latest,
)
from copiloto_core.services.rate_limit import (
    RateLimiter,
    build_rate_limit_middleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from copiloto_core.services.http_clients import close_all as _close_http_clients  # noqa: PLC0415

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

    PERF-024 (audit#4) — `Cache-Control: no-store` default:
      Endpoints v1 sirven datos tenant-scoped/PII y JAMÁS deberían
      caché en proxies o navegador. Default `no-store, no-cache`.
      Si un endpoint quiere opt-in a caching (e.g. estáticos),
      debe setear su propio `Cache-Control` ANTES de salir del
      handler — `setdefault` respeta lo que ya pusieron.
    """
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # PERF-024 — default no-store. Endpoints estáticos (admin SPA,
    # /openapi.json, etc.) pueden sobreescribir poniendo su propio
    # Cache-Control en la response antes del return.
    response.headers.setdefault(
        'Cache-Control', 'no-store, no-cache, must-revalidate, private',
    )
    return response


def create_app(modules: Iterable[CoreModule] = ()) -> FastAPI:
    """Construye la app FastAPI del core + monta módulos opt-in.

    Args:
      modules: lista de `CoreModule` declarados por los paquetes
        consumidores. Cada módulo aporta:
          - Su router HTTP (montado en `/v1/<code-with-dashes>`).
          - Sus capabilities (seedeadas en `app.capability` al startup).
          - Sus migrations SQL (aplicadas al startup vía runner Fase 6).
          - Sus static mounts (SPA propio, landing, etc.).
          - Su hook de activación por tenant (llamado al PATCH
            `tenant_modules.enabled=true`).

    Returns:
      Instancia de FastAPI lista para servir.

    Ejemplo:
      >>> from copiloto_core import create_app, CoreModule
      >>> from mi_modulo import module as mi_modulo
      >>> app = create_app(modules=[mi_modulo])

    Ver `docs/EXTENDING.md` para el contrato completo de módulo.
    """
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

    # ─── Montaje de módulos opt-in (Fase 5 audit#5) ──────────────────────
    # Cada CoreModule aporta su router, sus capabilities, sus static
    # mounts. Las migrations + el hook on_tenant_activate los maneja
    # el runner de migrations (Fase 6) y el endpoint de tenant_modules
    # (que invoca el hook al activar). Acá solo wireamos router + estáticos.
    modules_list = list(modules)
    _registered_module_codes: set[str] = set()
    for mod in modules_list:
        if mod.code in _registered_module_codes:
            raise ValueError(
                f'CoreModule.code duplicado: {mod.code!r}. Cada módulo debe '
                f'tener un code único en el deployment.',
            )
        _registered_module_codes.add(mod.code)
        api.include_router(mod.router, prefix=mod.url_prefix)
        for url_prefix, fs_path in mod.static_mounts.items():
            # `html=True` habilita SPA-fallback: cualquier URL no
            # encontrada en el directorio devuelve `index.html` (lo que
            # los SPA con client-side routing necesitan).
            api.mount(
                url_prefix,
                StaticFiles(directory=fs_path, html=True),
                name=f'{mod.code}{url_prefix.replace("/", "_")}',
            )

    # Exponemos los módulos registrados via `app.state.core_modules` para
    # que el runner de migrations + el endpoint de tenant_modules puedan
    # introspectar qué hay montado en este deployment.
    api.state.core_modules = tuple(modules_list)
    return api


app = create_app()
