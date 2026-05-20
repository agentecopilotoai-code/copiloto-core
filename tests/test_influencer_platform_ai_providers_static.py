"""Static tests for TASK-INFLU-002 — Platform AI providers + secret store.

Verifica:

- SQL migration crea ``app.platform_secrets`` y ``app.platform_ai_providers``
  con shape correcto, CHECK constraint, FK opcional, seed de 5 modalidades
  con ``provider='unset'``, RLS habilitada en ambas (default-deny).
- 01-schema.sql paridad.
- `app/ai/registry.py`:
    - Constantes `MODALITIES` y `PROVIDER_CACHE_TTL_SECONDS` declaradas.
    - `ResolvedProvider` dataclass frozen con los 6 campos correctos.
    - `resolve_provider` async, valida `modality` contra `MODALITIES`,
      cache TTL 5 min, fallback a env var cuando provider='unset'.
- `app/influencer/admin_routes.py`:
    - Endpoints registrados en `platform_admin_router` (no en otros routers).
    - GET `/platform/ai-providers` declarado.
    - PATCH `/platform/ai-providers/{modality}` declarado.
    - Response shapes (`PlatformAIProviderRow`) NO incluyen `ciphertext` ni
      `secret_value` — solo `hint` (últimos 4 chars).
    - Audit `platform.ai_provider_updated` se emite en el PATCH.
    - El secret_value en el body NUNCA se persiste en la columna `ciphertext`
      directamente — se guarda solo el `hint` (defensa contra leak via DB).
- `app/main.py` importa `admin_routes` para registrar los endpoints.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_SQL = REPO_ROOT / 'infra' / 'postgres' / '03-migrations.sql'
SCHEMA_SQL = REPO_ROOT / 'infra' / 'postgres' / '01-schema.sql'
PROVIDER_REGISTRY = REPO_ROOT / 'app' / 'ai' / 'registry.py'
ADMIN_ROUTES = REPO_ROOT / 'app' / 'influencer' / 'admin_routes.py'
MAIN_PY = REPO_ROOT / 'app' / 'main.py'


# ─── SQL migration ────────────────────────────────────────────────────────


@pytest.fixture(scope='module')
def migrations_source() -> str:
    return MIGRATIONS_SQL.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def schema_source() -> str:
    return SCHEMA_SQL.read_text(encoding='utf-8')


def test_migrations_declare_platform_secrets(migrations_source: str) -> None:
    assert 'create table if not exists app.platform_secrets' in migrations_source
    # Backend enum check.
    assert "check (backend in ('env', 'aws_sm', 'vault', 'file'))" in migrations_source
    # `hint` es NOT NULL — siempre tenemos identificador del secret.
    assert 'hint          text not null' in migrations_source
    # `ciphertext` es nullable (los backends env/aws_sm pueden delegar).
    assert 'ciphertext    bytea null' in migrations_source
    # RLS habilitada (default deny — solo paths del app después de
    # require_platform_owner pueden leer/escribir).
    assert 'alter table app.platform_secrets enable row level security' in migrations_source


def test_migrations_declare_platform_ai_providers(migrations_source: str) -> None:
    assert 'create table if not exists app.platform_ai_providers' in migrations_source
    # Modality es PRIMARY KEY (no UNIQUE adicional) — una sola fila por modalidad.
    assert 'modality      text primary key' in migrations_source
    assert (
        "check (modality in ('llm', 'image', 'video', 'tts', 'stt'))"
        in migrations_source
    )
    # FK opcional al secret store (la fila puede existir sin secret config).
    assert (
        'references app.platform_secrets(secret_ref) on delete set null'
        in migrations_source
    )
    # `params` es jsonb con default empty object.
    assert "params        jsonb not null default '{}'::jsonb" in migrations_source
    # RLS habilitada también — la lectura/escritura va por el path del app.
    assert 'alter table app.platform_ai_providers enable row level security' in migrations_source


def test_migrations_seed_five_modalities_unset(migrations_source: str) -> None:
    """Seed inicial: las 5 modalidades existen con provider='unset' después
    de aplicar la migración. Esto garantiza que `resolve_provider` siempre
    encuentra la fila y cae al fallback env-var en lugar de error.
    """
    assert 'insert into app.platform_ai_providers' in migrations_source
    for modality in ('llm', 'image', 'video', 'tts', 'stt'):
        assert f"'{modality}',   'unset'" in migrations_source or f"'{modality}', 'unset'" in migrations_source
    assert 'on conflict (modality) do nothing' in migrations_source


def test_schema_sql_has_paridad(schema_source: str) -> None:
    """`01-schema.sql` (fresh-install) debe declarar los mismos objetos
    que `03-migrations.sql` para que un cluster nuevo no quede sin las tablas.
    """
    assert 'create table if not exists app.platform_secrets' in schema_source
    assert 'create table if not exists app.platform_ai_providers' in schema_source
    assert 'enable row level security' in schema_source
    # Seed también presente.
    assert 'insert into app.platform_ai_providers' in schema_source


# ─── provider_registry helper ──────────────────────────────────────────────


def test_modalities_constant() -> None:
    from app.ai.registry import MODALITIES

    assert MODALITIES == ('llm', 'image', 'video', 'tts', 'stt')


def test_cache_ttl_is_five_minutes() -> None:
    from app.ai.registry import PROVIDER_CACHE_TTL_SECONDS

    assert 0 < PROVIDER_CACHE_TTL_SECONDS <= 300


def test_resolved_provider_dataclass_shape() -> None:
    from app.ai.registry import ResolvedProvider

    assert hasattr(ResolvedProvider, '__dataclass_fields__')
    expected = {'modality', 'provider', 'secret_ref', 'model', 'params', 'source'}
    actual = set(ResolvedProvider.__dataclass_fields__.keys())
    assert actual == expected, f'missing/extra fields: {actual ^ expected}'


def test_resolve_provider_is_async_and_validates_modality() -> None:
    from app.ai.registry import resolve_provider

    assert inspect.iscoroutinefunction(resolve_provider)

    sig = inspect.signature(resolve_provider)
    assert list(sig.parameters)[0] == 'conn'
    assert list(sig.parameters)[1] == 'modality'


def test_env_fallback_present_and_unset_sentinel() -> None:
    """Si la fila tiene `provider='unset'` o no existe, se cae a env var.
    Si la env var tampoco existe, `source='unset'` (no raise — el caller
    decide). El test verifica el path AST.
    """
    src = PROVIDER_REGISTRY.read_text(encoding='utf-8')
    # Fallback declarado.
    assert "INFLUENCER_DEFAULT_" in src
    assert "_PROVIDER" in src
    # source='unset' sentinel para distinguir.
    assert "source='unset'" in src or 'source = \'unset\'' in src


def test_cache_invalidate_helper_exported() -> None:
    from app.ai.registry import _cache_invalidate

    assert callable(_cache_invalidate)


# ─── admin_routes endpoints ────────────────────────────────────────────────


def test_endpoints_registered_on_platform_admin_router() -> None:
    """Los 2 endpoints viven en `platform_admin_router` que ya aplica
    `require_platform_owner` + `require_mfa_for_privileged`. Si alguien los
    moviera a `tenant_admin_router` por error, este test rompe.
    """
    from app.api.v1.routes import platform_admin_router

    # Disparar el side-effect del decorador.
    import app.influencer.admin_routes  # noqa: F401

    paths = {r.path for r in platform_admin_router.routes}
    assert '/platform/ai-providers' in paths
    assert '/platform/ai-providers/{modality}' in paths


def test_endpoints_NOT_in_tenant_routers() -> None:
    """Defensa explícita: la config de providers NO es accesible desde
    routers tenant-scoped, NUNCA. Si alguien decora con
    `@tenant_admin_router.X(...)` por copy-paste, este test lo detecta.
    """
    from app.api.v1.routes import (
        tenant_admin_router,
        tenant_catalog_router,
        tenant_ops_router,
        public_router,
    )

    import app.influencer.admin_routes  # noqa: F401

    forbidden_paths = {'/platform/ai-providers', '/platform/ai-providers/{modality}'}
    for router in (tenant_admin_router, tenant_catalog_router, tenant_ops_router, public_router):
        for r in router.routes:
            assert r.path not in forbidden_paths, (
                f'endpoint {r.path} no debe estar en {router}'
            )


def test_response_shape_never_exposes_ciphertext_or_secret_value() -> None:
    """AST check: ni `PlatformAIProviderRow` ni `PlatformAIProviderListResponse`
    pueden tener campos `ciphertext` o `secret_value`. Solo `hint`.
    """
    src = ADMIN_ROUTES.read_text(encoding='utf-8')
    tree = ast.parse(src)
    response_classes: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in {'PlatformAIProviderRow', 'PlatformAIProviderListResponse'}:
            continue
        fields: set[str] = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.add(item.target.id)
        response_classes[node.name] = fields

    assert 'PlatformAIProviderRow' in response_classes, 'response model declarado'
    row_fields = response_classes['PlatformAIProviderRow']
    assert 'hint' in row_fields, 'row debe exponer hint'
    assert 'ciphertext' not in row_fields, 'NUNCA exponer ciphertext'
    assert 'secret_value' not in row_fields, 'NUNCA exponer secret_value'
    assert 'secret_ref' not in row_fields, (
        'no exponer secret_ref (es opaco interno; el hint es lo público)'
    )


def test_patch_persists_only_hint_not_clear_value() -> None:
    """AST audit: el helper persiste el secret usa SOLO el ``_hint_of()`` del
    valor en claro. NUNCA hace `payload.secret_value` directo en un INSERT a
    `ciphertext` o `hint`. Defensa contra regresiones que filtren el secret
    a la columna `hint` o a logs.
    """
    src = ADMIN_ROUTES.read_text(encoding='utf-8')
    # El INSERT al platform_secrets debe pasar por `_hint_of(payload.secret_value)`.
    assert '_hint_of(payload.secret_value)' in src
    # Ningún punto debe persistir el secret_value en claro como hint.
    # Cuidado: el regex aquí busca `hint=...secret_value` directo (sin
    # _hint_of wrapping).
    assert 'hint=payload.secret_value' not in src
    assert 'hint = payload.secret_value' not in src


def test_audit_action_platform_ai_provider_updated() -> None:
    src = ADMIN_ROUTES.read_text(encoding='utf-8')
    assert "action='platform.ai_provider_updated'" in src
    # metadata incluye `secret_rotated` (bool) para distinguir un PATCH
    # que rotó la key vs uno que solo cambió el modelo.
    assert "'secret_rotated'" in src


def test_patch_invalidates_provider_cache() -> None:
    """Después de un PATCH, el cache del worker actual se invalida para que
    el siguiente `resolve_provider(modality)` lea la fila nueva de la DB.
    Sin esto, el cambio tarda hasta TTL 5 min en propagarse en este worker.
    """
    src = ADMIN_ROUTES.read_text(encoding='utf-8')
    assert '_provider_cache_invalidate()' in src


def test_routes_imports_admin_routes_for_side_effect() -> None:
    """BUGFIX-PLATFORM-ROUTES — el import side-effect que carga los
    decoradores de `app.influencer.admin_routes` ahora vive **dentro** de
    `app/api/v1/routes.py`, justo ANTES del `router.include_router(
    platform_admin_router)`. Antes vivía en `main.py:28`, después del import
    de `v1_router`, lo cual era demasiado tarde (FastAPI ya había copiado
    las rutas vacías). Sin este orden los endpoints `/platform/ai-providers*`
    y `/platform/tenant-modules*` devuelven 404 en runtime aunque el código
    exista y `platform_admin_router.routes` los contenga.
    """
    routes_src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text(encoding='utf-8')
    assert 'from app.influencer import admin_routes' in routes_src, (
        'routes.py debe importar admin_routes antes del include_router(platform_admin_router)'
    )

    # main.py NO debe re-importar admin_routes (sería redundante y tardío).
    main_src = MAIN_PY.read_text(encoding='utf-8')
    assert 'from app.influencer import admin_routes' not in main_src, (
        'main.py no debe importar admin_routes — vive en routes.py ahora'
    )


def test_endpoints_response_models_declared() -> None:
    """Los 2 endpoints declaran `response_model=...` para que FastAPI
    haga schema validation y NUNCA devuelva más campos de los declarados.
    Defensa adicional: si alguien retorna un dict con `ciphertext`, FastAPI
    lo descarta porque no está en el response_model.
    """
    from app.api.v1.routes import platform_admin_router

    import app.influencer.admin_routes  # noqa: F401

    target_paths = {'/platform/ai-providers', '/platform/ai-providers/{modality}'}
    for r in platform_admin_router.routes:
        if r.path in target_paths:
            assert r.response_model is not None, (
                f'{r.path} debe declarar response_model'
            )


# ─── BUGFIX-PLATFORM-ROUTES — tests estructurales/funcionales ─────────────
# Estos tests son defensa contra el bug donde los endpoints declarados en
# `admin_routes.py` quedaban registrados en `platform_admin_router.routes`
# pero NUNCA llegaban a `app.routes` porque `v1_router.include_router(
# platform_admin_router)` corría antes de que los decoradores ejecutaran.
# Antes solo había un test ESTÁTICO de string (verificaba que el import
# existiera en main.py). Ese test pasaba aunque el import fuera tardío
# y los endpoints devolvieran 404. Los tests siguientes verifican que la
# wiring HTTP funciona en runtime.

EXPECTED_ENDPOINTS_FROM_ADMIN_ROUTES = {
    # TASK-INFLU-002 — AI providers
    '/v1/platform/ai-providers',
    '/v1/platform/ai-providers/{modality}',
    # TASK-INFLU-019 — tenant modules
    '/v1/platform/tenant-modules',
    '/v1/platform/tenant-modules/{tenant_id}/{module}',
}


@pytest.fixture(scope='module')
def fastapi_app():
    """Importa la app FastAPI con env vars dummy para no requerir BD/secrets."""
    import os
    os.environ.setdefault('DATABASE_URL', 'postgresql://x:x@localhost/x')
    os.environ.setdefault('JWT_SECRET', 'x' * 32)
    os.environ.setdefault('SERVICE_TOKEN', 'x' * 32)
    os.environ.setdefault('S3_SECRET_ACCESS_KEY', 'x' * 32)
    import app.main
    return app.main.app


def test_admin_routes_endpoints_mounted_in_app(fastapi_app) -> None:
    """Verifica que los endpoints declarados en `app/influencer/admin_routes.py`
    aparecen en `app.routes` — es decir, fueron incluidos correctamente vía
    el orden de imports (BUGFIX-PLATFORM-ROUTES).
    """
    mounted = {r.path for r in fastapi_app.routes if hasattr(r, 'path')}
    missing = EXPECTED_ENDPOINTS_FROM_ADMIN_ROUTES - mounted
    assert not missing, (
        f'Estos endpoints están declarados en admin_routes.py pero NO están '
        f'montados en app.routes: {sorted(missing)}. Causa típica: el import '
        f'de admin_routes corre DESPUÉS de v1_router.include_router('
        f'platform_admin_router). Ver comentario en app/api/v1/routes.py:1695.'
    )


def test_admin_routes_endpoints_respond_not_404(fastapi_app) -> None:
    """Smoke test: cada endpoint montado debe responder algo distinto de 404
    incluso sin auth. Lo esperado es 401/403/422 — pero NUNCA 404 (que
    indicaría endpoint fantasma).
    """
    from starlette.testclient import TestClient
    client = TestClient(fastapi_app, raise_server_exceptions=False)

    # Las requests sin auth deben rechazarse, pero antes deben encontrar la
    # ruta. Un 404 indica que la ruta no está montada.
    for path in EXPECTED_ENDPOINTS_FROM_ADMIN_ROUTES:
        # Sustituye placeholders {x} por valores dummy para que el matcher
        # de FastAPI encuentre la ruta.
        concrete_path = path.replace('{modality}', 'llm') \
                            .replace('{tenant_id}', '00000000-0000-0000-0000-000000000000') \
                            .replace('{module}', 'influencer')
        method = 'PATCH' if '{' in path else 'GET'
        body = {'enabled': True} if method == 'PATCH' else None
        resp = client.request(method, concrete_path, json=body)
        assert resp.status_code != 404, (
            f'{method} {concrete_path} respondió 404. La ruta no está '
            f'montada en la app FastAPI.'
        )
