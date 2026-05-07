from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '.env.auth0.local'), env_file_encoding='utf-8', extra='ignore'
    )

    app_env: str = 'local'
    app_name: str = 'CopilotoIA Core'
    api_host: str = '0.0.0.0'
    api_port: int = 8000
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
    whatsapp_verify_token: str
    whatsapp_app_secret: str
    meta_graph_version: str = 'v23.0'
    meta_access_token: str | None = None
    s3_endpoint_url: str = 'http://minio:9000'
    s3_bucket: str = 'copilotoia-local'
    s3_access_key_id: str = 'copilotoia-minio'
    s3_secret_access_key: str
    rag_embedding_provider: str = 'local_hash'
    rag_embedding_model: str = 'copilotoia-local-hash-v1'
    rag_embedding_dimensions: int = 1536
    rag_chunk_max_tokens: int = 500
    rag_chunk_overlap_tokens: int = 80


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
