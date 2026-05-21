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

    app_env: str = 'local'
    app_name: str = 'CopilotoIA Core'
    api_host: str = '0.0.0.0'
    api_port: int = 8000
    log_level: str = Field(default='INFO', pattern='^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$')
    # BUG-219 (codex MEDIUM, 2026-05-18): toggle deploy-time para indicar que
    # hay un reverse proxy delante (nginx/ALB/Cloudflare) que SOBREESCRIBE
    # X-Forwarded-For. Cuando False (default), el rate limiter ignora XFF y
    # usa el peer IP de la conexión TCP (no spoofable). Setear True solo si
    # el operador confirmó que el proxy strip + reinjecta el header correcto.
    trust_proxy_forwarded_for: bool = False
    database_url: str
    redis_url: str = 'redis://redis:6379/0'
    jwt_issuer: str = 'copilotoia-local'
    jwt_audience: str = 'copilotoia-panel'
    jwt_secret: str = Field(min_length=16)
    auth0_domain: str | None = None
    auth0_issuer: str | None = None
    auth0_audience: str | None = None
    auth0_api_identifier: str | None = None
    auth0_admin_app_name: str | None = None
    auth0_admin_client_id: str | None = None
    auth0_admin_client_secret: str | None = None
    auth0_admin_client_secret_file: str | None = None
    # BUG-001: las credenciales SERVICE (M2M, `app_type=non_interactive`) son
    # las que autorizan `grant_type=client_credentials` contra Auth0 Management
    # API. El panel sigue usando AUTH0_ADMIN_* (regular_web, authorization_code
    # + refresh_token); el backend usa AUTH0_SERVICE_* para invitar miembros,
    # asignar roles y revocar acceso. configure-auth0.sh las escribe en
    # `.env.auth0.local` desde la app M2M `copilotoia-service-m2m`.
    auth0_service_app_name: str | None = None
    auth0_service_client_id: str | None = None
    auth0_service_client_secret: str | None = None
    auth0_service_client_secret_file: str | None = None
    auth0_service_audience: str | None = None
    auth0_callback_urls: str = 'http://localhost:3000/callback'
    auth0_logout_urls: str = 'http://localhost:3000'
    auth0_web_origins: str = 'http://localhost:3000'
    auth0_claims_namespace: str = 'https://copilotoia.com/claims/'
    auth0_jwks_cache_ttl_seconds: int = 300
    # Enforce MFA for privileged roles (admin/owner/platform_owner) when Auth0
    # is active.  Defaults to True so production stays protected.  Set to False
    # only in environments whose Auth0 plan lacks the MFA add-on (the factor
    # toggle and ``challengeWith`` Action are unavailable), so local/dev work
    # is not blocked by an MFA flow Auth0 cannot serve.
    mfa_enforcement_enabled: bool = True
    # SEC-010 fix — gate del bloque diagnóstico cross-tenant que loguea el
    # `actual_tenant_id` y `actual_status` de una conversación cuando un
    # caller pega un 404. Esa metadata puede pertenecer a OTRO tenant
    # (alguien pidió `/v1/tenants/A/conversations/<id-de-B>`) y exponerla
    # en logs operacionales filtra info cross-tenant a operadores que no
    # deberían verla. Default false. Para debugging de incidentes, setear
    # `DEBUG_CROSS_TENANT_DIAGNOSTICS=1` en el `.env` y reiniciar — los
    # logs habilitados solo deben mantenerse activos durante la
    # investigación (procedimiento operacional: documentar quién lo
    # activó, por qué, y desactivarlo cuando termine).
    debug_cross_tenant_diagnostics: bool = False
    service_token: str = Field(min_length=16)
    # AUDIT-48 (security quick win #3, 2026-05-18): rotación dual del
    # service_token (M2M trust). El callsite acepta CUALQUIERA de los dos —
    # operador setea `service_token_next` con el nuevo valor, rota clientes
    # M2M para que usen el nuevo, y cuando todos están migrados promueve
    # `service_token_next` a `service_token` y limpia `service_token_next`.
    # Sin downtime y sin un único secret en el wire. Si ambos están seteados
    # y matchean, ambos son válidos; el log de auditoría guarda cuál se usó.
    service_token_next: str | None = Field(default=None, min_length=16)
    # AUDIT-48 (security quick win #2): freshness check para webhooks de Meta.
    # Default 7 días (cubre retries agresivos de Meta sin permitir replay
    # arbitrario tras restore desde backup); 0 = desactivado (NO recomendado).
    webhook_meta_max_message_age_seconds: int = Field(default=7 * 24 * 3600, ge=0, le=30 * 24 * 3600)
    # AUDIT-46 (speed quick win #1, 2026-05-18): DB pool config expuesto. Antes
    # estaba hardcoded `max_size=10` en `app/db/pool.py:15`, lo cual significa
    # que un solo WS estancado o una query lenta podía saturar la app entera
    # sin posibilidad de mitigar sin redeploy. Exponer como settings permite
    # tunear por entorno (dev: bajo; prod: alto). `command_timeout` corta
    # queries colgadas a nivel pool (defensa en profundidad sobre statement_timeout).
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=10, ge=2, le=200)
    db_pool_command_timeout_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    # AUDIT-46 (speed quick win #2): rate limiter usa un dict in-memory de
    # buckets por (ip, tenant). Sin eviction, el dict crece sin tope con cada
    # IP nueva (BUG-219 cerró el spoofing trivial via XFF, pero el ataque por
    # rotación de NAT/IPv6 sigue creciendo memoria). Estos toggles limitan
    # la cantidad máxima de buckets vivos y los expira por inactividad.
    rate_limit_bucket_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    rate_limit_bucket_max_entries: int = Field(default=10_000, ge=100, le=1_000_000)
    meta_graph_version: str = 'v23.0'
    s3_endpoint_url: str = 'http://minio:9000'
    s3_bucket: str = 'copilotoia-local'
    knowledge_storage_backend: str = 'local'
    knowledge_storage_local_path: str = '/app/data/knowledge'
    knowledge_storage_s3_bucket_name: str | None = Field(
        default=None, validation_alias='KNOWLEDGE_STORAGE_S3_BUCKET'
    )
    knowledge_file_max_bytes: int = 10 * 1024 * 1024
    knowledge_allowed_mime_types: str = (
        'text/plain,text/markdown,text/csv,application/json,application/pdf,'
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    extraction_timeout_seconds: int = 60
    extraction_max_attempts: int = 3
    s3_access_key_id: str = 'copilotoia-minio'
    s3_secret_access_key: str
    # Master key (Fernet) usada para cifrar/descifrar las API keys de los
    # proveedores IA transversales en `app.platform_secrets.ciphertext`. Si
    # falta, los endpoints `/v1/platform/ai-providers*` rechazan rotaciones
    # y smoke tests con un mensaje claro. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # En dev local lo crea `scripts/generate-local-secrets.sh`.
    ai_provider_master_key: str | None = Field(
        default=None,
        validation_alias='AI_PROVIDER_MASTER_KEY',
        min_length=44,  # Fernet keys son 32-byte base64-urlsafe → 44 chars
    )
    rag_embedding_provider: str = 'local_hash'
    rag_embedding_model: str = 'copilotoia-local-hash-v1'
    rag_embedding_dimensions: int = 1536
    # API key for real embedding providers (openai / anthropic / ollama).
    # Leave unset to use local_hash in development.
    rag_embedding_api_key: str | None = Field(default=None, validation_alias='RAG_EMBEDDING_API_KEY')
    rag_chunk_max_tokens: int = 500
    rag_chunk_overlap_tokens: int = 80
    # Answer engine: 'template' | 'local_llm' | 'cascade' | 'cloud_llm'
    # cascade: template → LLM local → cloud LLM (si configurado) → handoff
    answer_engine: str = Field(default='template', pattern='^(template|local_llm|cascade|cloud_llm)$')
    local_llm_base_url: str = 'http://host.docker.internal:11434'
    local_llm_model: str = 'llama3.2:3b'
    local_llm_timeout_seconds: int = 30
    # Umbrales para modo cascade
    cascade_template_min_score: float = 0.55   # template responde solo si está muy seguro
    cascade_llm_min_score: float = 0.12        # LLM intenta si hay al menos un chunk relevante
    # Cloud LLM (Claude API / OpenAI) — tier-3 del cascade cuando Ollama no está disponible,
    # o motor primario cuando answer_engine=cloud_llm.
    cloud_llm_provider: str | None = None      # 'claude' | 'openai'
    cloud_llm_model: str = 'claude-sonnet-4-6'
    cloud_llm_api_key: str | None = Field(default=None, validation_alias='CLOUD_LLM_API_KEY')
    cloud_llm_timeout_seconds: int = 30
    # Tiempo en horas que puede estar un handoff abierto sin agente antes de
    # que el bot retome la conversación automáticamente. 0 = desactivado.
    bot_reopen_after_hours: float = 2.0
    # TASK-0057: operator alerts. URL pública del panel para construir el link
    # al Operations Desk en los avisos enviados al equipo. Si está vacío, los
    # canales que usan link (email/webhook) caen al texto sin URL.
    admin_panel_public_url: str = 'http://localhost:3000'
    alerts_smtp_host: str | None = None
    alerts_smtp_port: int = 587
    alerts_smtp_username: str | None = None
    alerts_smtp_password: str | None = None
    alerts_smtp_from: str | None = None
    alerts_smtp_use_tls: bool = True
    alerts_max_attempts: int = 5
    alerts_retry_base_seconds: int = 60
    # TASK-0059: rate limiting + circuit breaker
    rate_limit_per_min: int = Field(default=60, ge=1)
    rate_limit_webhook_per_min: int = Field(default=600, ge=1)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_cooldown_seconds: float = Field(default=30.0, ge=1.0)
    # TASK-0060: observabilidad — endpoint /metrics restringido a IPs allowlisted.
    # Lista separada por comas; vacío = endpoint inaccesible. No soporta CIDR.
    observability_allowed_ips: str = ''
    # Puerto en el que cada proceso worker expone su /metrics (cada worker corre
    # en un container separado, por lo que pueden compartir el mismo puerto
    # interno y diferenciarse por el `targets:` de Prometheus).
    worker_metrics_port: int = Field(default=9100, ge=1, le=65535)
    # TASK-0061: política de retención GDPR. El worker corre 1x al día a esta
    # hora UTC. ``retention_page_size`` controla el ``LIMIT`` por iteración del
    # DELETE/UPDATE paginado. ``retention_anomaly_threshold_pct`` dispara una
    # señal de auditoría si una corrida borra más del N% del histórico.
    retention_run_hour_utc: int = Field(default=3, ge=0, le=23)
    retention_page_size: int = Field(default=5000, ge=100, le=50000)
    retention_anomaly_threshold_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    # TASK-0065: alerta automática cuando la DLQ outbound crece. Se evalúa cada
    # tick del scheduler contando mensajes ``status='failed'`` en la última hora
    # por tenant. Si supera el umbral, encola un ``operator_alerts(kind=
    # 'outbound_dlq_threshold')`` con el preview de los últimos 5 errores.
    dlq_alert_threshold: int = Field(default=10, ge=1)
    dlq_alert_window_minutes: int = Field(default=60, ge=1, le=1440)
    # TASK-0070: CDN-distributed embeddable web widget. ``web_widget_api_base``
    # is the origin the widget hits for /v1/web/chat/*; it MUST be set to the
    # public API origin in production because the CDN host that serves
    # widget.js (e.g. cdn.copilotoia.com) doesn't proxy the API. The widget
    # reads it from ``data-api-base`` on the snippet.
    web_widget_api_base: str = 'http://localhost:8000'
    web_widget_cdn_url: str = 'https://cdn.copilotoia.com/widget/v1/widget.js'

    # AUDIT-49 / re-audit §1.9 (2026-05-18): coerce empty string → None para
    # `service_token_next`. El default operacional de rotación es: setear
    # `SERVICE_TOKEN_NEXT=<nuevo>` en `.env`, rotar clientes M2M, promover
    # a `SERVICE_TOKEN`, y desactivar el slot. Si el operador "desactiva"
    # dejando la línea como `SERVICE_TOKEN_NEXT=` (vacío), Pydantic veía
    # `""` (str de 0 chars) y reventaba con `ValidationError: string too
    # short` (min_length=16) → app no arranca. Ahora `""` se mapea a `None`
    # antes de la validación de min_length, así "borrar la línea" y
    # "dejar la línea vacía" tienen el mismo efecto operacional.
    @field_validator('service_token_next', mode='before')
    @classmethod
    def _empty_service_token_next_is_none(cls, value):
        if isinstance(value, str) and value.strip() == '':
            return None
        return value

    @property
    def knowledge_storage_bucket(self) -> str:
        return self.knowledge_storage_s3_bucket_name or self.s3_bucket

    @property
    def knowledge_allowed_mime_types_set(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.knowledge_allowed_mime_types.split(',')
            if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
