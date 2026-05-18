"""BUG-096: `brand_logo_url` se seteaba a `stored.source_uri`
(`file://`/`s3://`), URL que el browser no puede renderizar como
`<img src>` → admin shell mostraba imagen rota.

Fix:
- Nuevo helper `read_media_file(...)` en `media_storage.py` lee bytes
  desde `local` (`file://`) o `s3` (`get_object`).
- Nuevo endpoint `GET /v1/tenants/{tenant_id}/media/{asset_id}/content`
  en `tenant_ops_router` sirve los bytes con `Content-Type =
  asset.mime_type` + `Cache-Control: private, max-age=600`.
- Helper `tenant_brand_logo_proxy_url(tenant_id, asset_id) -> str`
  construye la URL canónica.
- `upload_tenant_brand_logo` ahora guarda en
  `tenant_settings.brand_logo_url` la URL del proxy, no
  `stored.source_uri`.
"""
from __future__ import annotations

from pathlib import Path

import pytest


MEDIA_STORAGE = Path('app/services/media_storage.py')
ROUTES = Path('app/api/v1/routes.py')


# ───── read_media_file helper ────────────────────────────────────────────


def test_bug_096_media_storage_exports_read_media_file():
    src = MEDIA_STORAGE.read_text()
    assert 'def read_media_file(' in src, (
        "BUG-096: debe existir `read_media_file(...)` en media_storage.py "
        "como mirror simétrico de `store_media_file`."
    )


def test_bug_096_read_media_file_supports_local_and_s3_backends():
    src = MEDIA_STORAGE.read_text()
    fn_idx = src.find('def read_media_file(')
    next_topdef = src.find('\ndef delete_media_file', fn_idx)
    block = src[fn_idx:next_topdef] if next_topdef > 0 else src[fn_idx:]
    assert "backend == 'local'" in block, (
        "BUG-096: `read_media_file` debe manejar backend='local'."
    )
    assert "backend == 's3'" in block, (
        "BUG-096: `read_media_file` debe manejar backend='s3'."
    )
    # Local lee `file://<path>` desde source_uri.
    assert "source_uri[len('file://'):]" in block, (
        "BUG-096: lectura local debe stripear el prefijo `file://`."
    )
    # S3 usa get_object(Bucket, Key).
    assert 'client.get_object(' in block and 'Bucket=bucket' in block, (
        "BUG-096: lectura s3 debe usar `client.get_object(Bucket=bucket, Key=object_key)`."
    )


# ───── Proxy URL helper ──────────────────────────────────────────────────


def test_bug_096_tenant_brand_logo_proxy_url_helper_exists():
    src = ROUTES.read_text()
    assert 'def tenant_brand_logo_proxy_url(' in src, (
        "BUG-096: debe existir `tenant_brand_logo_proxy_url(tenant_id, asset_id)` "
        "como única fuente de la ruta del proxy (evita drift entre upload + endpoint)."
    )
    helper_idx = src.find('def tenant_brand_logo_proxy_url(')
    next_decl = src.find('\n\n', helper_idx + 1)
    block = src[helper_idx:next_decl]
    assert "f'/v1/tenants/{tenant_id}/media/{asset_id}/content'" in block, (
        "BUG-096: el helper debe devolver "
        "`/v1/tenants/{tenant_id}/media/{asset_id}/content`."
    )


# ───── Proxy endpoint ────────────────────────────────────────────────────


def test_bug_096_proxy_endpoint_exists_on_tenant_ops_router():
    src = ROUTES.read_text()
    decorator = "@tenant_ops_router.get('/tenants/{tenant_id}/media/{asset_id}/content')"
    assert decorator in src, (
        "BUG-096: el endpoint proxy debe estar en `tenant_ops_router` (agent+) "
        "para que la admin shell, viewer-like UIs y agentes vean el logo."
    )


def test_bug_096_proxy_endpoint_validates_tenant_access_and_rls():
    src = ROUTES.read_text()
    fn_idx = src.find('async def get_tenant_media_content(')
    assert fn_idx > 0
    next_def = src.find('\n\n@', fn_idx)
    block = src[fn_idx:next_def]
    # Defensa tenant-scope.
    assert 'ensure_tenant_access(request, tenant_id, conn)' in block, (
        "BUG-096: el endpoint debe llamar `ensure_tenant_access` para validar "
        "membresía en el tenant antes de servir bytes."
    )
    # RLS GUC.
    assert "set_config('app.tenant_id', $1, true)" in block, (
        "BUG-096: el endpoint debe setear `app.tenant_id` GUC para que RLS "
        "sobre `app.media_assets` aplique al SELECT."
    )
    # Lookup por (tenant_id, asset_id).
    assert 'where tenant_id = $1 and id = $2' in block, (
        "BUG-096: el SELECT del asset debe filtrar por `(tenant_id, id)` — "
        "defensa contra cross-tenant lookup vía asset_id adivinado."
    )
    # 404 cuando no existe.
    assert "status_code=404, detail='Media asset not found'" in block, (
        "BUG-096: 404 cuando el asset no existe en el tenant."
    )
    # Cache-Control private (no proxy compartido cachea).
    assert "'Cache-Control': 'private, max-age=600'" in block, (
        "BUG-096: response debe llevar `Cache-Control: private, max-age=600`."
    )


# ───── Upload usa el proxy URL ───────────────────────────────────────────


def test_bug_096_upload_persists_proxy_url_not_source_uri():
    src = ROUTES.read_text()
    fn_idx = src.find('async def upload_tenant_brand_logo(')
    assert fn_idx > 0
    next_def = src.find('\n\n# BUG-096', fn_idx)
    if next_def < 0:
        next_def = src.find('\n\n@', fn_idx)
    block = src[fn_idx:next_def]
    # La asignación nueva: proxy URL.
    assert 'new_url = tenant_brand_logo_proxy_url(tenant_id, asset_id)' in block, (
        "BUG-096: el upload debe usar `tenant_brand_logo_proxy_url(...)` "
        "como valor de `brand_logo_url`, no `stored.source_uri`."
    )
    # Asegurarse que ya NO se persiste el source_uri raw.
    assert 'new_url = stored.source_uri' not in block, (
        "BUG-096: regresión — `new_url = stored.source_uri` debe haberse "
        "removido. Persistir `file://` o `s3://` rompe el `<img src>` del browser."
    )


# ───── Smoke unit test (skip si import falla en local sin deps) ──────────


def test_bug_096_read_media_file_local_roundtrip(tmp_path):
    """Roundtrip rápido sobre `local`: escribir un PNG dummy en disco y
    verificar que `read_media_file` lo devuelve idéntico.
    """
    try:
        from app.services.media_storage import read_media_file
    except ModuleNotFoundError as exc:
        pytest.skip(f'env missing deps: {exc}')

    payload = b'\x89PNG\r\n\x1a\n' + b'dummy-image-bytes'
    target = tmp_path / 'logo.png'
    target.write_bytes(payload)

    out = read_media_file(
        storage_backend='local',
        object_key='media/tenant-x/asset-x/abc-logo.png',
        source_uri=f'file://{target}',
        bucket=None,
        settings=None,  # noqa: S106 — `local` no usa settings
    )
    assert out == payload


def test_bug_096_read_media_file_local_missing_raises_file_not_found(tmp_path):
    """Si el file:// apunta a un path inexistente, `read_media_file` debe
    raise `FileNotFoundError` (el endpoint lo mapea a 404).
    """
    try:
        from app.services.media_storage import read_media_file
    except ModuleNotFoundError as exc:
        pytest.skip(f'env missing deps: {exc}')

    missing = tmp_path / 'does-not-exist.png'
    with pytest.raises(FileNotFoundError):
        read_media_file(
            storage_backend='local',
            object_key='media/tenant-x/asset-x/abc-missing.png',
            source_uri=f'file://{missing}',
            bucket=None,
            settings=None,
        )
