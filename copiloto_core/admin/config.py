"""Settings del BFF admin (`copiloto_core.admin`).

Lee del mismo `.env` / `.env.auth0.local` que el resto del core. Forzamos
fail-fast al startup cuando `state_secret` no está explícito (BUG-200):
sin esto, con N workers de uvicorn cada worker generaba un secret efímero
distinto, rechazando los cookies/state OAuth emitidos por otro worker.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '.env.auth0.local'), env_file_encoding='utf-8', extra='ignore'
    )

    app_name: str = 'CopilotoIA Core'
    app_env: str = 'local'
    jwt_secret: str | None = None
    admin_session_secret: str | None = None
    auth0_domain: str | None = None
    auth0_issuer: str | None = None
    auth0_audience: str | None = None
    auth0_api_identifier: str | None = None
    auth0_admin_app_name: str | None = None
    auth0_admin_client_id: str | None = None
    auth0_admin_client_secret: str | None = None
    auth0_admin_client_secret_file: str | None = None
    auth0_callback_urls: str = 'http://localhost:3000/callback'
    auth0_logout_urls: str = 'http://localhost:3000/admin/,http://localhost:3000'
    auth0_web_origins: str = 'http://localhost:3000'
    auth0_claims_namespace: str = 'https://copilotoia.com/claims/'
    admin_core_api_base_url: str = 'http://127.0.0.1:8000'

    # v1.5.4: a dónde redirigir el browser después del login OAuth exitoso
    # y después del logout. Defaults pensados para consumer flow
    # (admin_panel=False): `/dashboard` viene del scaffolder, `/` es la
    # landing. El repo del core override-ea a `/admin/` poniendo
    # POST_LOGIN_REDIRECT_URL=/admin/ en su .env porque su admin SPA
    # sigue siendo la home post-login.
    post_login_redirect_url: str = '/dashboard'
    post_logout_redirect_url: str = '/'
    # MFA enforcement default ON SIEMPRE (secure-by-default).
    #
    # Historia: v1.6.1 había puesto default OFF en local para evitar un
    # loop infinito del SPA cuando MFA Policy de Auth0 estaba desactivada.
    # v1.6.3 revierte eso por anti-pattern: "fail-open silencioso" oculta
    # al operador que MFA NO está activa cuando él cree que sí.
    #
    # Si tu loop es el infinito de auto-logout en dev local:
    #   1. RECOMENDADO: activá MFA Policy en Auth0 (Dashboard →
    #      Security → Multi-Factor Auth → Always require). Una sola vez.
    #   2. Si querés skip MFA para iterar rápido en dev, agregá a tu
    #      `.env` explícito (que vos lees y entendés que es solo dev):
    #        MFA_ENFORCEMENT_ENABLED=false
    #
    # Ver docs/AUTH0.md § "Activar MFA Policy" para los pasos.
    mfa_enforcement_enabled: bool = True
    # P0-3 (audit 2026-05-27) — Redis URL para session store cross-worker.
    # Si None, el BFF usa InMemorySessionStore (single-worker only). En
    # docker-compose ya viene `redis://redis:6379/0`; en prod multi-worker
    # es obligatorio.
    redis_url: str | None = None
    # Prefijo de keys en Redis para sessions del BFF — evita colisión si
    # comparten Redis con otros servicios del mismo cluster.
    bff_session_redis_prefix: str = 'copilotoia:admin:session:'

    @property
    def state_secret(self) -> str:
        """Secret HMAC para firmar el state cookie y los signed payloads.

        Fail-fast: si ni `admin_session_secret` ni `jwt_secret` están
        seteados Y `app_env != 'local'`, levantamos. Caer a un secret
        random per-proceso en producción rompe sesiones multi-worker.
        """
        secret = self.admin_session_secret or self.jwt_secret
        if secret:
            return secret
        if self.app_env != 'local':
            raise RuntimeError(
                'admin BFF: ADMIN_SESSION_SECRET (o JWT_SECRET) requerido en '
                f"app_env={self.app_env!r}. Sin esto, multi-worker rechaza "
                'cookies entre instancias.',
            )
        # Solo en local aceptamos derivar un secret estable del proceso.
        # Estable = mismo hash del cwd para que reinicios en dev no rompan
        # sesiones abiertas.
        import hashlib
        return hashlib.sha256(b'admin-bff-local-dev').hexdigest()

    @property
    def cookies_secure(self) -> bool:
        """`secure=True` para cookies cuando NO estamos en `local`."""
        return self.app_env != 'local'


@lru_cache
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
