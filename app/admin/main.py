from fastapi import FastAPI

from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    api = FastAPI(title=f'{settings.app_name} Admin Panel', version='0.1.0')
    api.include_router(admin_router)
    return api


app = create_app()
