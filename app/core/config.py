from functools import lru_cache
from pydantic import Field
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
    auth0_callback_urls: str = 'http://localhost:3000/callback'
    auth0_logout_urls: str = 'http://localhost:3000'
    auth0_web_origins: str = 'http://localhost:3000'
    auth0_claims_namespace: str = 'https://copilotoia.com/claims/'
    auth0_jwks_cache_ttl_seconds: int = 300
    service_token: str = Field(min_length=16)
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
