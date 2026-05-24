"""Tests unitarios para `app/services/influencer_storage.py`.

Cubre las ramas que no requieren un backend S3 real:
  - `_ext_for_mime`: mime → extensión (defaults a `.bin`).
  - `_build_object_key`: convención de path por kind (face-variations,
    references) + reemplazo del `tenants/{tid}/knowledge` por
    `tenants/{tid}/influencer`.
  - `store_face_variation_asset` y `store_reference_asset` para backend
    `local` (tmp_path como root).
  - Backend desconocido → ValueError.
  - `read_local_asset`: hit, miss y path-traversal protection.
  - `s3_get_asset_bytes`: sin bucket → None; mock cliente que devuelve None
    en ClientError.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import influencer_storage as iso


# ── Helpers de fixtures ────────────────────────────────────────────────────


@pytest.fixture
def local_settings(tmp_path):
    """Devuelve un Settings stub con `knowledge_storage_local_path` apuntando
    a un tmp_path. influencer_storage solo lee ese atributo en backend=local.
    """
    return SimpleNamespace(knowledge_storage_local_path=str(tmp_path))


@pytest.fixture
def local_config():
    """Config del tenant con backend=local (defaults)."""
    return {'backend': 'local'}


# ── _ext_for_mime ──────────────────────────────────────────────────────────


def test_ext_for_mime_known_types():
    assert iso._ext_for_mime('image/png') == '.png'
    assert iso._ext_for_mime('image/jpeg') in ('.jpg', '.jpeg')
    assert iso._ext_for_mime('image/webp') == '.webp'


def test_ext_for_mime_handles_parameters():
    # mime con `;charset=utf-8` se debe limpiar antes de mapear.
    assert iso._ext_for_mime('image/png; charset=utf-8') == '.png'


def test_ext_for_mime_empty_or_unknown():
    assert iso._ext_for_mime('') == '.bin'
    assert iso._ext_for_mime('application/vnd.bogus') == '.bin'


# ── _build_object_key ──────────────────────────────────────────────────────


def test_build_object_key_default_prefix_replaces_knowledge_with_influencer():
    key = iso._build_object_key(
        tenant_id='t-1', kind='face-variations', request_id='req-1', idx=0,
        mime='image/png', prefix=None,
    )
    assert key == 'tenants/t-1/influencer/face-variations/req-1/0.png'


def test_build_object_key_custom_prefix_appends_influencer():
    key = iso._build_object_key(
        tenant_id='t-1', kind='references', request_id='persona-9', idx=42,
        mime='image/jpeg', prefix='custom/path',
    )
    # `normalize_object_prefix` con custom prefix devuelve `custom/path`
    # tal cual (no añade tenants/{tid}/). Sobre eso se concatena
    # `/influencer/references/persona-9/42.{ext}`.
    assert key.startswith('custom/path/influencer/references/persona-9/42.')
    assert key.endswith(('.jpg', '.jpeg'))


def test_build_object_key_unknown_mime_uses_bin():
    key = iso._build_object_key(
        tenant_id='t', kind='references', request_id='p', idx=0,
        mime='application/bogus', prefix=None,
    )
    assert key.endswith('.bin')


# ── store_face_variation_asset (local) ─────────────────────────────────────


def test_store_face_variation_asset_local_writes_file_and_returns_metadata(
    tmp_path, local_settings, local_config,
):
    data = b'\x89PNG\r\n\x1a\n_fake'
    result = iso.store_face_variation_asset(
        data=data,
        tenant_id='tenant-1',
        request_id='req-99',
        idx=0,
        mime='image/png',
        settings=local_settings,
        config=local_config,
    )

    assert result.storage_backend == 'local'
    assert result.bucket is None
    assert result.size_bytes == len(data)
    assert result.mime == 'image/png'
    assert result.object_key == 'tenants/tenant-1/influencer/face-variations/req-99/0.png'

    # El archivo debe existir en tmp_path con esos bytes.
    written = Path(tmp_path) / result.object_key
    assert written.is_file()
    assert written.read_bytes() == data
    assert result.source_uri.startswith('file://')


def test_store_face_variation_asset_local_rejects_path_traversal(
    tmp_path, local_settings,
):
    """Si el prefix del tenant sale del root, debe levantar ValueError."""
    bad_config = {'backend': 'local', 'prefix': '../../etc/passwd'}
    # normalize_object_prefix sanitiza pero verificamos defensa en profundidad
    # — si por algún motivo la key resuelta sale del root, abortamos.
    # Con prefix '..' la key normalizada en realidad queda dentro del tenant
    # path, pero invocamos con un object_key construido manualmente vía
    # monkeypatch para ejercitar la guarda.
    with patch.object(iso, '_build_object_key', return_value='../../../escape/file.png'):
        with pytest.raises(ValueError, match='Invalid influencer storage path'):
            iso.store_face_variation_asset(
                data=b'x', tenant_id='t', request_id='r', idx=0, mime='image/png',
                settings=local_settings, config=bad_config,
            )


def test_store_reference_asset_local_uses_references_path(
    tmp_path, local_settings, local_config,
):
    data = b'jpeg-bytes'
    result = iso.store_reference_asset(
        data=data,
        tenant_id='tenant-9',
        persona_id='persona-42',
        idx=0,
        mime='image/jpeg',
        settings=local_settings,
        config=local_config,
    )
    assert result.object_key.startswith('tenants/tenant-9/influencer/references/persona-42/')
    assert result.object_key.endswith(('.jpg', '.jpeg'))
    assert result.storage_backend == 'local'
    assert (Path(tmp_path) / result.object_key).read_bytes() == data


# ── Backend desconocido / errores ──────────────────────────────────────────


def test_store_asset_unknown_backend_raises(local_settings):
    with pytest.raises(ValueError, match='Unsupported influencer storage backend'):
        iso.store_face_variation_asset(
            data=b'x', tenant_id='t', request_id='r', idx=0, mime='image/png',
            settings=local_settings, config={'backend': 'azure'},
        )


def test_store_asset_s3_without_bucket_raises(local_settings):
    with pytest.raises(ValueError, match='S3 backend requires tenant config.bucket'):
        iso.store_face_variation_asset(
            data=b'x', tenant_id='t', request_id='r', idx=0, mime='image/png',
            settings=local_settings, config={'backend': 's3'},
        )


# ── S3 backend (mockeado) ──────────────────────────────────────────────────


def test_store_face_variation_asset_s3_uses_put_object_with_metadata(
    local_settings,
):
    """Verifica que el backend S3 invoca put_object con el ContentType y los
    metadata correctos (incluido `kind: face_variation`)."""
    fake_client = MagicMock()
    config = {
        'backend': 's3',
        'bucket': 'my-bucket',
        'region': 'us-east-1',
        'endpoint_url': 'https://s3.amazonaws.com',
        'access_key_id': 'AKIA',
        'secret_access_key': 'secret',
    }
    with patch.object(iso, '_s3_client', return_value=fake_client) as mock_client:
        result = iso.store_face_variation_asset(
            data=b'png-bytes', tenant_id='t-1', request_id='r-1', idx=0,
            mime='image/png', settings=local_settings, config=config,
        )

    assert result.storage_backend == 's3'
    assert result.bucket == 'my-bucket'
    assert result.source_uri.startswith('s3://my-bucket/')
    mock_client.assert_called_once()
    put_kwargs = fake_client.put_object.call_args.kwargs
    assert put_kwargs['Bucket'] == 'my-bucket'
    assert put_kwargs['ContentType'] == 'image/png'
    assert put_kwargs['Metadata']['kind'] == 'face_variation'
    assert put_kwargs['Metadata']['tenant_id'] == 't-1'


def test_store_reference_asset_s3_uses_reference_kind_metadata(local_settings):
    fake_client = MagicMock()
    config = {'backend': 's3', 'bucket': 'b'}
    with patch.object(iso, '_s3_client', return_value=fake_client):
        iso.store_reference_asset(
            data=b'data', tenant_id='t', persona_id='p', idx=0,
            mime='image/jpeg', settings=local_settings, config=config,
        )
    put_kwargs = fake_client.put_object.call_args.kwargs
    # store_reference_asset usa metadata_kind='reference'.
    assert put_kwargs['Metadata']['kind'] == 'reference'


# ── read_local_asset ───────────────────────────────────────────────────────


def test_read_local_asset_hit(tmp_path, local_settings):
    sub = Path(tmp_path) / 'tenants/t/influencer/face-variations/r/0.png'
    sub.parent.mkdir(parents=True)
    sub.write_bytes(b'data')
    result = iso.read_local_asset(
        settings=local_settings,
        object_key='tenants/t/influencer/face-variations/r/0.png',
    )
    assert result is not None
    assert result.read_bytes() == b'data'


def test_read_local_asset_miss_returns_none(local_settings):
    result = iso.read_local_asset(
        settings=local_settings, object_key='tenants/x/inexistent.png',
    )
    assert result is None


def test_read_local_asset_path_traversal_returns_none(local_settings):
    # Path que resuelve fuera del root debe devolver None.
    result = iso.read_local_asset(
        settings=local_settings, object_key='../../../etc/passwd',
    )
    assert result is None


# ── s3_get_asset_bytes ─────────────────────────────────────────────────────


def test_s3_get_asset_bytes_without_bucket_returns_none(local_settings):
    result = iso.s3_get_asset_bytes(
        settings=local_settings, object_key='k', config={},
    )
    assert result is None


def test_s3_get_asset_bytes_client_error_returns_none(local_settings):
    fake_client = MagicMock()
    fake_client.get_object.side_effect = Exception('NoSuchKey')
    config = {'bucket': 'b'}
    with patch.object(iso, '_s3_client', return_value=fake_client):
        result = iso.s3_get_asset_bytes(
            settings=local_settings, object_key='k', config=config,
        )
    assert result is None


def test_s3_get_asset_bytes_success_returns_tuple(local_settings):
    fake_body = MagicMock()
    fake_body.read.return_value = b'image-bytes'
    fake_client = MagicMock()
    fake_client.get_object.return_value = {
        'Body': fake_body, 'ContentType': 'image/png',
    }
    config = {'bucket': 'b'}
    with patch.object(iso, '_s3_client', return_value=fake_client):
        result = iso.s3_get_asset_bytes(
            settings=local_settings, object_key='k', config=config,
        )
    assert result == (b'image-bytes', 'image/png')


def test_s3_get_asset_bytes_default_mime_when_missing(local_settings):
    fake_body = MagicMock()
    fake_body.read.return_value = b'bytes'
    fake_client = MagicMock()
    fake_client.get_object.return_value = {'Body': fake_body}  # no ContentType
    with patch.object(iso, '_s3_client', return_value=fake_client):
        result = iso.s3_get_asset_bytes(
            settings=local_settings, object_key='k', config={'bucket': 'b'},
        )
    assert result == (b'bytes', 'application/octet-stream')
