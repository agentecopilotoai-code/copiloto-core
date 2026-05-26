"""Settings del core (`app.core.config`).

Solo expone settings que CADA módulo del core consume hoy. Settings que
existían pre-purga para chatbot/influencer/whatsapp/widget se eliminaron
(ver M7 de la auditoría). Los módulos opt-in que se instalen sobre el
core declaran sus propios settings (Pydantic permite múltiples
`BaseSettings` con el mismo `.env`).
"""
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '.env.auth0.local'),
        env_file_encoding='utf-8',
        extra='ignore',
        populate_by_name=True,
    )

    # ─── App / runtime ────────────────────────────────────────────────────
    app_env: str = 'local'
    app_name: str = 'CopilotoIA Core'
    api_host: str = '0.0.0.0'
    api_port: int = 8000
    log_level: str = Field(default='INFO', pattern='^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$')

    # BUG-219 (codex MEDIUM): toggle deploy-time para indicar que hay un
    # reverse proxy delante (nginx/ALB/Cloudflare) que SOBREESCRIBE
    # X-Forwarded-For. Cuando False (default), el rate limiter ignora XFF
    # y usa el peer IP de la conexión TCP (no spoofable). Setear True
    # solo si el operador confirmó que el proxy strip + reinjecta el
    # header correcto.
    trust_proxy_forwarded_for: bool = False

    # ─── DB ───────────────────────────────────────────────────────────────
    database_url: str
    # AUDIT-46: DB pool config expuesto. Antes hardcoded `max_size=10`
    # en `app/db/pool.py` — un solo WS estancado podía saturar la app.
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=10, ge=2, le=200)
    db_pool_command_timeout_seconds: float = Field(default=30.0, ge=1.0, le=600.0)

    # ─── Auth / Auth0 ─────────────────────────────────────────────────────
    jwt_issuer: str = 'copilotoia-local'
    jwt_audience: str = 'copilotoia-panel'
    jwt_secret: str = Field(min_length=16)
    auth0_domain: str | None = None
    auth0_issuer: str | None = None
    auth0_audience: str | None = None
    auth0_admin_client_id: str | None = None
    auth0_admin_client_secret: str | None = None
    auth0_admin_client_secret_file: str | None = None
    auth0_callback_urls: str = 'http://localhost:3000/callback'
    auth0_logout_urls: str = 'http://localhost:3000'
    auth0_web_origins: str = 'http://localhost:3000'
    auth0_claims_namespace: str = 'https://copilotoia.com/claims/'
    auth0_jwks_cache_ttl_seconds: int = 300

    # M59 — Auth0 Management API (M2M app `copilotoia-service-m2m`).
    # Cuando estos están seteados, `app.services.auth0_admin` puede
    # invitar usuarios reales (email + password reset link), bloquear
    # logins, resetear MFA, borrar users de Auth0. Sin esto, los
    # handlers de members funcionan en modo LOCAL ONLY (sólo
    # `app.user_tenant_roles`, sin propagar a Auth0).
    auth0_service_client_id: str | None = None
    auth0_service_client_secret: str | None = None
    auth0_service_client_secret_file: str | None = None
    # Cache TTL del Management API token (Auth0 los emite con 24h
    # por default, pero refrescamos un poco antes por safety).
    auth0_mgmt_token_cache_ttl_seconds: int = 60 * 60 * 20  # 20h

    # MFA enforcement para roles privilegiados (admin/owner/platform_owner).
    # Setear False solo en envs cuya tier Auth0 no incluye MFA add-on.
    mfa_enforcement_enabled: bool = True

    # M60/A-003 — toggle de compat para el header `x-admin-user-email`.
    #
    # ANTES (M58): el BFF inyectaba este header al proxyar al Core porque
    # Auth0 no incluía `email` en el access_token. El Core leía ese header
    # como fallback cuando el JWT no tenía email. SPOOFABLE por cualquier
    # caller con un access_token Auth0 que pegue directo al Core.
    #
    # AHORA: el Auth0 Action emite el claim `email` namespaced en el
    # access_token (ver scripts/configure-auth0.sh post-M60). El Core lee
    # el email del JWT firmado y NO necesita el header.
    #
    # Default True por COMPAT con instalaciones existentes que aún no
    # re-deployaron el Action. Pasar a False una vez verificado que el
    # access_token trae el claim (chequeable en `/admin/api/diagnostics`
    # o leyendo cualquier audit log con `actor_email` populated).
    auth0_trust_admin_email_header: bool = True

    # ─── Service token (M2M) ──────────────────────────────────────────────
    service_token: str = Field(min_length=16)
    # AUDIT-48: rotación dual del service_token. El callsite acepta
    # CUALQUIERA de los dos. "" → None para permitir "desactivar" via .env.
    service_token_next: str | None = Field(default=None, min_length=16)

    # ─── Rate limiting ────────────────────────────────────────────────────
    rate_limit_per_min: int = Field(default=60, ge=1)
    rate_limit_webhook_per_min: int = Field(default=600, ge=1)
    # AUDIT-46: cap + TTL del dict in-memory de buckets para evitar
    # memory leak por rotación NAT/IPv6.
    rate_limit_bucket_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    rate_limit_bucket_max_entries: int = Field(default=10_000, ge=100, le=1_000_000)

    # ─── S3 / blobs del admin (branding logo, exports CSV) ────────────────
    s3_endpoint_url: str = 'http://minio:9000'
    s3_bucket: str = 'copilotoia-local'
    s3_access_key_id: str = 'copilotoia-minio'
    s3_secret_access_key: str

    # ─── AI providers — master key para cifrar API keys ───────────────────
    # Master key (Fernet) usada para cifrar/descifrar API keys de los
    # proveedores IA transversales en `app.platform_secrets.ciphertext`.
    # Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # En dev local lo crea `scripts/generate-local-secrets.sh`.
    ai_provider_master_key: str | None = Field(
        default=None,
        validation_alias='AI_PROVIDER_MASTER_KEY',
        min_length=44,  # Fernet keys: 32-byte base64-urlsafe → 44 chars
    )

    # ─── Observability ────────────────────────────────────────────────────
    # `/metrics` restringido a IPs allowlisted. Lista separada por comas;
    # vacío = endpoint inaccesible. No soporta CIDR.
    observability_allowed_ips: str = ''

    @field_validator('service_token_next', mode='before')
    @classmethod
    def _empty_service_token_next_is_none(cls, value):
        if isinstance(value, str) and value.strip() == '':
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
