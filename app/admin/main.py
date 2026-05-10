from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin.config import get_admin_settings
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.pool import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await db.connect(settings.database_url)
    yield
    await db.close()


def create_app() -> FastAPI:
    settings = get_admin_settings()
    api = FastAPI(title=f'{settings.app_name} Admin Panel', version='0.1.0', lifespan=lifespan)
    api.include_router(admin_router)
    return api


app = create_app()
