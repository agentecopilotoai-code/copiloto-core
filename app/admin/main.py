from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin.config import get_admin_settings
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.pool import db


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - lifespan only runs in a real ASGI server
    from app.admin.session_store import close_session_store
    from app.services.http_clients import close_all as close_http_clients

    settings = get_settings()
    configure_logging(settings.log_level)
    await db.connect(settings.database_url)
    try:
        yield
    finally:
        await db.close()
        await close_session_store()  # P0-3 — cerrar conn Redis si aplica
        await close_http_clients()   # PERF-001 — cerrar httpx singletons


def create_app() -> FastAPI:  # pragma: no cover - factory exercised via app/main.py
    settings = get_admin_settings()
    api = FastAPI(title=f'{settings.app_name} Admin Panel', version='0.1.0', lifespan=lifespan)
    api.include_router(admin_router)
    return api


app = create_app()  # pragma: no cover - module-level boot
