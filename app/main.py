from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.routes import router as v1_router
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.pool import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    await db.connect(settings.database_url)
    yield
    await db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)
    api.include_router(admin_router)
    api.include_router(v1_router)
    return api


app = create_app()
