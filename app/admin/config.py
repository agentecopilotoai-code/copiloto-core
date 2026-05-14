from functools import lru_cache
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROCESS_STATE_SECRET = secrets.token_urlsafe(32)


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '.env.auth0.local'), env_file_encoding='utf-8', extra='ignore'
    )

    app_name: str = 'CopilotoIA Core'
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
    # Mirrors ``Settings.mfa_enforcement_enabled``: when False the BFF stops
    # gating privileged sessions on MFA.  Keep both in sync via the shared
    # ``MFA_ENFORCEMENT_ENABLED`` env var.
    mfa_enforcement_enabled: bool = True

    @property
    def state_secret(self) -> str:
        return self.admin_session_secret or self.jwt_secret or _PROCESS_STATE_SECRET


@lru_cache
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
