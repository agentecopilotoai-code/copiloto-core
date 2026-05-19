"""More pure-helper tests for `app/api/v1/routes.py`.

Targets the early-module helpers: secret refs, knowledge storage config,
verify_token_hash, payload extractors, parse_json_object, normalizers,
is_service_or_support, _tenant_db_role_meets, media_url_from_payload.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


# ───────── tenant_secret_ref ─────────────────────────────────────────────


def test_tenant_secret_ref_format():
    from app.api.v1.routes import tenant_secret_ref
    tid = UUID('11111111-1111-1111-1111-111111111111')
    assert tenant_secret_ref(tid, 'api_key') == \
        'secrets/tenants/11111111-1111-1111-1111-111111111111/api_key'


def test_tenant_knowledge_s3_secret_ref():
    from app.api.v1.routes import tenant_knowledge_s3_secret_ref
    tid = uuid4()
    out = tenant_knowledge_s3_secret_ref(tid)
    assert out.startswith(f'secrets/tenants/{tid}/')
    assert out.endswith('/knowledge_s3_secret_access_key')


# ───────── write_tenant_secret rejects traversal ─────────────────────────


def test_write_tenant_secret_rejects_traversal():
    from app.api.v1.routes import write_tenant_secret
    with pytest.raises(HTTPException) as exc_info:
        write_tenant_secret('secrets/../etc/passwd', 'value')
    assert exc_info.value.status_code == 400


def test_write_tenant_secret_rejects_empty(tmp_path, monkeypatch):
    from app.api.v1.routes import write_tenant_secret
    monkeypatch.chdir(tmp_path)
    # 'secrets/' alone strips to empty → rejected
    with pytest.raises(HTTPException):
        write_tenant_secret('secrets/', 'value')


def test_write_tenant_secret_writes_file(tmp_path, monkeypatch):
    """Successful write paths to a relative file under .secrets/ in cwd."""
    from app.api.v1.routes import write_tenant_secret
    monkeypatch.chdir(tmp_path)
    write_tenant_secret('secrets/test/my_key', 'the-value\n')
    written = (tmp_path / '.secrets' / 'test' / 'my_key').read_text()
    assert written == 'the-value'


# ───────── default_knowledge_storage_config ──────────────────────────────


def test_default_knowledge_storage_config():
    from app.api.v1.routes import default_knowledge_storage_config
    tid = uuid4()
    cfg = default_knowledge_storage_config(tid)
    assert cfg['backend'] == 'local'
    assert cfg['bucket'] is None
    assert cfg['prefix'] == f'tenants/{tid}/knowledge'
    assert cfg['secret_ref'] is None


# ───────── normalize_knowledge_storage_config ───────────────────────────


def test_normalize_knowledge_storage_config_passes_through_known_keys():
    from app.api.v1.routes import normalize_knowledge_storage_config
    tid = uuid4()
    out = normalize_knowledge_storage_config(tid, {
        'backend': 's3',
        'bucket': 'my-bucket',
        'region': 'us-east-1',
        'endpoint_url': 'https://s3.example.com',
        'prefix': f'tenants/{tid}/knowledge/custom',
        'access_key_id': 'AKIA...',
        'secret_ref': 'secrets/tenants/x/y',
    })
    assert out['backend'] == 's3'
    assert out['bucket'] == 'my-bucket'
    assert out['region'] == 'us-east-1'


def test_normalize_knowledge_storage_config_json_string():
    from app.api.v1.routes import normalize_knowledge_storage_config
    tid = uuid4()
    out = normalize_knowledge_storage_config(tid, '{"backend": "s3", "bucket": "bk"}')
    assert out['backend'] == 's3'
    assert out['bucket'] == 'bk'


def test_normalize_knowledge_storage_config_invalid_json_returns_default():
    from app.api.v1.routes import normalize_knowledge_storage_config
    tid = uuid4()
    out = normalize_knowledge_storage_config(tid, 'not json')
    assert out['backend'] == 'local'


def test_normalize_knowledge_storage_config_unknown_backend_falls_back():
    """Anything other than 'local' / 's3' is normalized to 'local'."""
    from app.api.v1.routes import normalize_knowledge_storage_config
    tid = uuid4()
    out = normalize_knowledge_storage_config(tid, {'backend': 'gcs'})
    assert out['backend'] == 'local'


def test_normalize_knowledge_storage_config_bad_prefix_falls_back():
    from app.api.v1.routes import normalize_knowledge_storage_config
    tid = uuid4()
    out = normalize_knowledge_storage_config(tid, {'prefix': '/'})
    # Falls back to the tenant-default prefix
    assert out['prefix'] == f'tenants/{tid}/knowledge'


# ───────── verify_token_hash ──────────────────────────────────────────────


def test_verify_token_hash_is_sha256():
    import hashlib
    from app.api.v1.routes import verify_token_hash
    assert verify_token_hash('hello') == hashlib.sha256(b'hello').digest()
    assert verify_token_hash('') == hashlib.sha256(b'').digest()


# ───────── whatsapp_phone_number_id_from_payload ─────────────────────────


def test_whatsapp_phone_number_id_from_payload_returns_id():
    from app.api.v1.routes import whatsapp_phone_number_id_from_payload
    payload = {
        'entry': [
            {'changes': [
                {'value': {'metadata': {'phone_number_id': '1234567'}}},
            ]},
        ],
    }
    assert whatsapp_phone_number_id_from_payload(payload) == '1234567'


def test_whatsapp_phone_number_id_from_payload_missing():
    from app.api.v1.routes import whatsapp_phone_number_id_from_payload
    assert whatsapp_phone_number_id_from_payload({}) is None
    assert whatsapp_phone_number_id_from_payload({'entry': []}) is None
    assert whatsapp_phone_number_id_from_payload(
        {'entry': [{'changes': [{'value': {'metadata': {}}}]}]},
    ) is None


# ───────── media_url_from_payload ────────────────────────────────────────


def test_media_url_from_payload_media_url():
    from app.api.v1.routes import media_url_from_payload
    assert media_url_from_payload({'media_url': '  https://x/y.jpg  '}) == 'https://x/y.jpg'


def test_media_url_from_payload_link_fallback():
    from app.api.v1.routes import media_url_from_payload
    assert media_url_from_payload({'link': 'https://x/y.jpg'}) == 'https://x/y.jpg'


def test_media_url_from_payload_none_for_invalid():
    from app.api.v1.routes import media_url_from_payload
    assert media_url_from_payload(None) is None
    assert media_url_from_payload('not a dict') is None
    assert media_url_from_payload({}) is None
    assert media_url_from_payload({'media_url': ''}) is None
    assert media_url_from_payload({'media_url': '   '}) is None
    assert media_url_from_payload({'media_url': 123}) is None


# ───────── parse_json_object ─────────────────────────────────────────────


def test_parse_json_object_dict_passthrough():
    from app.api.v1.routes import parse_json_object
    d = {'k': 'v'}
    assert parse_json_object(d) == d


def test_parse_json_object_json_string():
    from app.api.v1.routes import parse_json_object
    assert parse_json_object('{"k": 1}') == {'k': 1}


def test_parse_json_object_invalid_returns_default():
    from app.api.v1.routes import parse_json_object
    assert parse_json_object('garbage') == {}
    assert parse_json_object('garbage', default={'fb': 1}) == {'fb': 1}
    assert parse_json_object(None) == {}
    assert parse_json_object(42) == {}


# ───────── normalize_knowledge_documents ─────────────────────────────────


def test_normalize_knowledge_documents_maps_all():
    from app.api.v1.routes import normalize_knowledge_documents
    rows = [
        {'id': '1', 'title': 'A', 'metadata': {'k': 1}},
        {'id': '2', 'title': 'B', 'metadata': '{"x": 2}'},
    ]
    out = normalize_knowledge_documents(rows)
    assert len(out) == 2
    assert out[0]['metadata'] == {'k': 1}
    assert out[1]['metadata'] == {'x': 2}


def test_normalize_knowledge_documents_empty_list():
    from app.api.v1.routes import normalize_knowledge_documents
    assert normalize_knowledge_documents([]) == []


# ───────── metadata_extracted_text ───────────────────────────────────────


def test_metadata_extracted_text_returns_string():
    from app.api.v1.routes import metadata_extracted_text
    assert metadata_extracted_text({'extracted_text': 'hola'}) == 'hola'


def test_metadata_extracted_text_json_string():
    from app.api.v1.routes import metadata_extracted_text
    assert metadata_extracted_text('{"extracted_text": "json"}') == 'json'


def test_metadata_extracted_text_none_for_missing():
    from app.api.v1.routes import metadata_extracted_text
    assert metadata_extracted_text(None) is None
    assert metadata_extracted_text({}) is None
    assert metadata_extracted_text({'extracted_text': 123}) is None


# ───────── is_service_or_support ─────────────────────────────────────────


def test_is_service_or_support_true_for_service():
    from app.api.v1.routes import is_service_or_support
    request = SimpleNamespace(state=SimpleNamespace(
        actor_type='service', support_mode=False,
    ))
    assert is_service_or_support(request) is True


def test_is_service_or_support_true_for_support_mode():
    from app.api.v1.routes import is_service_or_support
    request = SimpleNamespace(state=SimpleNamespace(
        actor_type='user', support_mode=True,
    ))
    assert is_service_or_support(request) is True


def test_is_service_or_support_false_for_user():
    from app.api.v1.routes import is_service_or_support
    request = SimpleNamespace(state=SimpleNamespace(
        actor_type='user', support_mode=False,
    ))
    assert is_service_or_support(request) is False


def test_is_service_or_support_false_for_anonymous():
    from app.api.v1.routes import is_service_or_support
    request = SimpleNamespace(state=SimpleNamespace())
    assert is_service_or_support(request) is False


# ───────── _tenant_db_role_meets ─────────────────────────────────────────


def test_tenant_db_role_meets():
    from app.api.v1.routes import _tenant_db_role_meets
    assert _tenant_db_role_meets('owner', 'admin') is True
    assert _tenant_db_role_meets('admin', 'admin') is True
    assert _tenant_db_role_meets('manager', 'admin') is False
    assert _tenant_db_role_meets('viewer', 'agent') is False
    assert _tenant_db_role_meets('agent', 'viewer') is True


def test_tenant_db_role_meets_none_role():
    from app.api.v1.routes import _tenant_db_role_meets
    assert _tenant_db_role_meets(None, 'agent') is False


def test_tenant_db_role_meets_unknown_role():
    from app.api.v1.routes import _tenant_db_role_meets
    assert _tenant_db_role_meets('platform_owner', 'admin') is False  # not in tenant table


# ───────── public_knowledge_storage_config ───────────────────────────────


def test_public_knowledge_storage_config_adds_metadata():
    from app.api.v1.routes import public_knowledge_storage_config
    tid = uuid4()
    out = public_knowledge_storage_config(tid, {'backend': 'local'})
    assert 'secret_configured' in out
    assert 'effective_bucket' in out
    assert out['backend'] == 'local'


def test_public_knowledge_storage_config_s3_with_secret(monkeypatch, tmp_path):
    """When secret_ref points to an existing file, secret_configured is True."""
    from app.api.v1.routes import public_knowledge_storage_config
    from app.services import whatsapp as wa
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'sec_test').write_text('AKIASECRET')

    def fake_paths(name):
        return [secret_dir / name]

    monkeypatch.setattr(wa, '_candidate_secret_paths', fake_paths)
    tid = uuid4()
    out = public_knowledge_storage_config(
        tid, {'backend': 's3', 'bucket': 'b', 'secret_ref': 'secrets/sec_test'},
    )
    assert out['secret_configured'] is True


def test_public_knowledge_storage_config_no_secret_ref():
    from app.api.v1.routes import public_knowledge_storage_config
    tid = uuid4()
    out = public_knowledge_storage_config(tid, {'backend': 'local'})
    assert out['secret_configured'] is False
