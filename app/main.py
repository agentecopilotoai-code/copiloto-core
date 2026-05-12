from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.v1.routes import router as v1_router
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


def _is_web_widget_path(path: str) -> bool:
    return path.startswith('/v1/web/')


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)

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

    api.include_router(admin_router)
    api.include_router(v1_router)
    return api


app = create_app()
