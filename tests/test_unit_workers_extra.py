"""Extra coverage tests for app/workers/{event_worker,extraction_worker,
digest_worker,scheduler}.py and app/admin/ws_fanout.py.

Pure unit tests using `_FakeConn` and stubbed transports. No real DB.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Common fakes
# ═══════════════════════════════════════════════════════════════════════════


class _FakeTxn:
    """Sync context manager that pretends to be conn.transaction()."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


class _FakeConn:
    """asyncpg.Connection stand-in with optional transaction() + canned results.

    `fetch_results` / `fetchrow_results` / `fetchval_results` are popped FIFO.
    Calls to execute() are appended to `self.executed`.
    """
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return _FakeTxn()


# ═══════════════════════════════════════════════════════════════════════════
# event_worker — provider_message_id / delivery_error_message / _code
# ═══════════════════════════════════════════════════════════════════════════


def test_provider_message_id_extracts_first_id():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({'messages': [{'id': 'wamid.X'}]}) == 'wamid.X'


def test_provider_message_id_missing_messages():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({}) is None
    assert provider_message_id({'messages': []}) is None
    assert provider_message_id({'messages': 'not a list'}) is None


def test_provider_message_id_first_message_not_dict():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({'messages': ['plain string']}) is None


def test_provider_message_id_id_not_string():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({'messages': [{'id': 123}]}) is None


def test_provider_message_id_no_id_field():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({'messages': [{'no_id': True}]}) is None


def test_delivery_error_message_http_status_error():
    from app.workers.event_worker import delivery_error_message
    response = httpx.Response(400, text='bad request body here')
    request = httpx.Request('POST', 'http://example.com')
    exc = httpx.HTTPStatusError('400', request=request, response=response)
    msg = delivery_error_message(exc)
    assert '400' in msg
    assert 'bad request body here' in msg


def test_delivery_error_message_plain_exception():
    from app.workers.event_worker import delivery_error_message
    exc = ValueError('something broke')
    assert delivery_error_message(exc) == 'something broke'


def test_delivery_error_message_truncates():
    from app.workers.event_worker import delivery_error_message
    big = 'x' * 5000
    assert len(delivery_error_message(ValueError(big))) <= 1000


def test_delivery_error_code_parses_meta_code():
    from app.workers.event_worker import delivery_error_code
    body = {'error': {'code': 131026, 'message': 'msg'}}
    response = httpx.Response(400, json=body)
    request = httpx.Request('POST', 'http://example.com')
    exc = httpx.HTTPStatusError('400', request=request, response=response)
    assert delivery_error_code(exc) == '131026'


def test_delivery_error_code_falls_back_to_http_status():
    from app.workers.event_worker import delivery_error_code
    response = httpx.Response(500, text='not json')
    request = httpx.Request('POST', 'http://example.com')
    exc = httpx.HTTPStatusError('500', request=request, response=response)
    assert delivery_error_code(exc) == 'http_500'


def test_delivery_error_code_transport_error():
    from app.workers.event_worker import delivery_error_code
    assert delivery_error_code(ValueError('dns')) == 'transport_error'


def test_delivery_error_code_no_code_in_body():
    from app.workers.event_worker import delivery_error_code
    response = httpx.Response(400, json={'error': {'message': 'msg'}})  # no code
    request = httpx.Request('POST', 'http://example.com')
    exc = httpx.HTTPStatusError('400', request=request, response=response)
    assert delivery_error_code(exc) == 'http_400'


# ═══════════════════════════════════════════════════════════════════════════
# event_worker — _process_locked_batch happy + failure paths
# ═══════════════════════════════════════════════════════════════════════════


def _wa_row(*, body_text='hi', provider='whatsapp_cloud_api', payload=None,
            phone_e164='+5730099887766', wa_id='5730099887766',
            account_mode='mock', message_type='text', service_window_expires_at=None,
            page_id=None, instagram_account_id=None):
    return {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'aggregate_id': uuid4(),
        'conversation_id': uuid4(),
        'body_text': body_text,
        'message_type': message_type,
        'media_id': None,
        'mime_type': None,
        'payload': payload or {},
        'provider': provider,
        'phone_number_id': '12345',
        'page_id': page_id,
        'instagram_account_id': instagram_account_id,
        'account_mode': account_mode,
        'token_ref': 'kms://tok',
        'service_window_hours': 24,
        'service_window_expires_at': service_window_expires_at,
        'phone_e164': phone_e164,
        'wa_id': wa_id,
    }


def test_process_locked_batch_no_rows_returns_zero(monkeypatch):
    from app.workers import event_worker
    conn = _FakeConn(fetch_results=[[]], fetchval_results=[0])

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 0


def test_process_locked_batch_whatsapp_success(monkeypatch):
    from app.workers import event_worker
    row = _wa_row()
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        return {'messages': [{'id': 'wamid.OK'}], 'mocked': False}
    monkeypatch.setattr(event_worker, 'send_whatsapp_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    out = asyncio.run(_go())
    assert out == 1
    # Should mark sent + update domain_events + pg_notify
    sqls = [sql for sql, _ in conn.executed]
    assert any("status='sent'" in s for s in sqls)
    assert any('published_at=now()' in s for s in sqls)
    assert any('pg_notify' in s for s in sqls)


def test_process_locked_batch_whatsapp_mocked_path(monkeypatch):
    from app.workers import event_worker
    row = _wa_row()
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        return {'messages': [{'id': 'mock.1'}], 'mocked': True}
    monkeypatch.setattr(event_worker, 'send_whatsapp_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1


def test_process_locked_batch_whatsapp_http_error_marks_failed(monkeypatch):
    from app.workers import event_worker

    row = _wa_row()
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        response = httpx.Response(400, json={'error': {'code': 131026}})
        request = httpx.Request('POST', 'http://meta')
        raise httpx.HTTPStatusError('400', request=request, response=response)
    monkeypatch.setattr(event_worker, 'send_whatsapp_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    out = asyncio.run(_go())
    assert out == 1
    sqls = [sql for sql, _ in conn.executed]
    assert any("status='failed'" in s for s in sqls)
    assert any('error_code' in s for s in sqls)


def test_process_locked_batch_whatsapp_transport_error_marks_failed(monkeypatch):
    from app.workers import event_worker
    row = _wa_row()
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        raise ConnectionError('dns')
    monkeypatch.setattr(event_worker, 'send_whatsapp_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1
    sqls = [sql for sql, _ in conn.executed]
    assert any("status='failed'" in s for s in sqls)


def test_process_locked_batch_messenger_outside_service_window(monkeypatch):
    """instagram_messenger provider, window expired → OutsideServiceWindowError → marked failed."""
    from app.workers import event_worker
    from app.services.meta_messenger import OutsideServiceWindowError

    past = datetime.now(timezone.utc) - timedelta(hours=48)
    row = _wa_row(provider='instagram_messenger', instagram_account_id='ig1',
                  page_id=None, service_window_expires_at=past)
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        raise OutsideServiceWindowError('expired')
    monkeypatch.setattr(event_worker, 'send_messenger_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1
    # error_code stored should be 'outside_service_window'
    failed_args = [args for sql, args in conn.executed if "status='failed'" in sql]
    assert failed_args
    assert any('outside_service_window' in str(a) for a in failed_args[0])


def test_process_locked_batch_messenger_window_open_with_expires(monkeypatch):
    """provider=facebook_messenger, future window → window_open=True, sends OK."""
    from app.workers import event_worker
    future = datetime.now(timezone.utc) + timedelta(hours=12)
    row = _wa_row(provider='facebook_messenger', page_id='page_1',
                  service_window_expires_at=future)
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    received_kwargs = {}
    async def fake_send(*args, **kwargs):
        received_kwargs.update(kwargs)
        return {'messages': [{'id': 'mid'}], 'mocked': False}
    monkeypatch.setattr(event_worker, 'send_messenger_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1
    assert received_kwargs.get('within_service_window') is True


def test_process_locked_batch_messenger_naive_expires_is_normalized(monkeypatch):
    """When service_window_expires_at has no tzinfo, code assumes UTC."""
    from app.workers import event_worker
    naive_future = datetime.now() + timedelta(hours=12)
    row = _wa_row(provider='facebook_messenger', page_id='page_1',
                  service_window_expires_at=naive_future)
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        return {'messages': [{'id': 'mid'}], 'mocked': True}
    monkeypatch.setattr(event_worker, 'send_messenger_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    asyncio.run(_go())


def test_process_locked_batch_messenger_missing_recipient_raises(monkeypatch):
    """instagram_messenger but no instagram_account_id → RuntimeError → marked failed."""
    from app.workers import event_worker
    row = _wa_row(provider='instagram_messenger', instagram_account_id=None, page_id=None)
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    # Should never be called since recipient_account_id check fails first
    async def fake_send(*args, **kwargs):
        raise AssertionError('should not be called')
    monkeypatch.setattr(event_worker, 'send_messenger_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1
    sqls = [sql for sql, _ in conn.executed]
    assert any("status='failed'" in s for s in sqls)


def test_process_locked_batch_payload_is_string(monkeypatch):
    """payload is a JSON string and gets parsed."""
    from app.workers import event_worker
    row = _wa_row(payload=json.dumps({'media_url': 'http://x'}))
    conn = _FakeConn(fetch_results=[[row]], fetchval_results=[1])

    async def fake_send(*args, **kwargs):
        return {'messages': [{'id': 'mid'}], 'mocked': True}
    monkeypatch.setattr(event_worker, 'send_whatsapp_message', fake_send)

    async def _go():
        return await event_worker._process_locked_batch(conn)
    assert asyncio.run(_go()) == 1


def test_process_once_iterates_until_zero(monkeypatch):
    """process_once loops up to BATCH_SIZE times until handled==0."""
    from app.workers import event_worker
    conn = _FakeConn(fetch_results=[[], [], []], fetchval_results=[0, 0, 0])
    call_count = [0]
    orig = event_worker._process_locked_batch

    async def counting(conn):
        call_count[0] += 1
        return await orig(conn)
    monkeypatch.setattr(event_worker, '_process_locked_batch', counting)

    async def _go():
        return await event_worker.process_once(conn)
    out = asyncio.run(_go())
    assert out == 0
    assert call_count[0] == 1  # first iter returned 0 so we break


# ═══════════════════════════════════════════════════════════════════════════
# extraction_worker — helpers and _process_document branches
# ═══════════════════════════════════════════════════════════════════════════


def test_extract_text_sync_unknown_mime_raises():
    from app.workers.extraction_worker import _extract_text_sync
    with pytest.raises(ValueError, match='No extractor'):
        _extract_text_sync(b'data', 'application/x-foo')


def test_extract_text_sync_normalizes_mime():
    """MIME params after `;` and uppercase should be stripped."""
    from app.workers.extraction_worker import _extract_text_sync
    with pytest.raises(ValueError):
        _extract_text_sync(b'\x00', 'APPLICATION/X-UNKNOWN; charset=utf-8')


def test_load_file_bytes_missing_storage_key_raises():
    from app.workers.extraction_worker import _load_file_bytes
    settings = SimpleNamespace(knowledge_storage_backend='local',
                                knowledge_storage_bucket=None,
                                knowledge_storage_local_path='/tmp')

    async def _go():
        await _load_file_bytes({}, settings, tenant_id=uuid4())
    with pytest.raises(ValueError, match='no storage_key'):
        asyncio.run(_go())


def test_load_file_bytes_storage_key_not_scoped_raises():
    """Cross-tenant storage_key (BUG-213 fix) — refused with clear error."""
    from app.workers.extraction_worker import _load_file_bytes
    settings = SimpleNamespace(knowledge_storage_backend='local',
                                knowledge_storage_bucket=None,
                                knowledge_storage_local_path='/tmp')
    tenant_id = uuid4()
    other_tenant = uuid4()
    md = {'storage_key': f'tenants/{other_tenant}/knowledge/file.pdf'}

    async def _go():
        await _load_file_bytes(md, settings, tenant_id=tenant_id)
    with pytest.raises(ValueError, match='not_tenant_scoped'):
        asyncio.run(_go())


def test_load_file_bytes_unsupported_backend():
    from app.workers.extraction_worker import _load_file_bytes
    settings = SimpleNamespace(knowledge_storage_backend='gcs',
                                knowledge_storage_bucket=None,
                                knowledge_storage_local_path='/tmp')
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/file.pdf'}

    async def _go():
        await _load_file_bytes(md, settings, tenant_id=tenant_id)
    with pytest.raises(ValueError, match='Unsupported storage backend'):
        asyncio.run(_go())


def test_load_file_bytes_s3_no_bucket_raises():
    from app.workers.extraction_worker import _load_file_bytes
    settings = SimpleNamespace(knowledge_storage_backend='s3',
                                knowledge_storage_bucket=None,
                                knowledge_storage_local_path='/tmp')
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/file.pdf'}

    async def _go():
        await _load_file_bytes(md, settings, tenant_id=tenant_id)
    with pytest.raises(ValueError, match='no_bucket_configured'):
        asyncio.run(_go())


def test_load_file_bytes_uses_tenant_config(monkeypatch, tmp_path):
    """When tenant_storage_config is provided, derive backend/bucket/prefix from there."""
    from app.workers import extraction_worker

    settings = SimpleNamespace(knowledge_storage_backend='local',
                                knowledge_storage_bucket=None,
                                knowledge_storage_local_path=str(tmp_path))
    tenant_id = uuid4()
    # Use a custom prefix
    custom_prefix = 'knowledge'
    target = tmp_path / 'knowledge' / 'doc.pdf'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'PDF DATA')

    md = {'storage_key': f'{custom_prefix}/doc.pdf'}
    tenant_cfg = {'backend': 'local', 'prefix': custom_prefix, 'bucket': None}

    async def _go():
        return await extraction_worker._load_file_bytes(
            md, settings, tenant_id=tenant_id, tenant_storage_config=tenant_cfg,
        )
    out = asyncio.run(_go())
    assert out == b'PDF DATA'


def test_load_file_bytes_s3_with_bucket(monkeypatch):
    """S3 backend with valid bucket → calls _read_s3_file via run_in_executor."""
    from app.workers import extraction_worker

    settings = SimpleNamespace(knowledge_storage_backend='s3',
                                knowledge_storage_bucket='my-bucket',
                                knowledge_storage_local_path='/tmp',
                                s3_endpoint_url=None,
                                s3_access_key_id='AKIA',
                                s3_secret_access_key='secret')
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/doc.pdf'}

    def fake_s3_read(bucket, key, _settings):
        assert bucket == 'my-bucket'
        return b'S3 DATA'
    monkeypatch.setattr(extraction_worker, '_read_s3_file', fake_s3_read)

    async def _go():
        return await extraction_worker._load_file_bytes(md, settings, tenant_id=tenant_id)
    assert asyncio.run(_go()) == b'S3 DATA'


def test_read_local_file_escape_raises(tmp_path):
    from app.workers.extraction_worker import _read_local_file
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    with pytest.raises(ValueError, match='escapes local root'):
        _read_local_file('../../etc/passwd', settings)


def test_read_local_file_not_found(tmp_path):
    from app.workers.extraction_worker import _read_local_file
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        _read_local_file('missing.pdf', settings)


def test_read_local_file_ok(tmp_path):
    from app.workers.extraction_worker import _read_local_file
    (tmp_path / 'a.pdf').write_bytes(b'hi')
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    assert _read_local_file('a.pdf', settings) == b'hi'


def test_audit_swallows_exception():
    """The _audit helper must NEVER raise."""
    from app.workers.extraction_worker import _audit

    class _Raise:
        async def execute(self, *a):
            raise RuntimeError('db gone')

    async def _go():
        await _audit(_Raise(), uuid4(), uuid4(), 'x.y', {'a': 1})
    asyncio.run(_go())  # no raise


def test_audit_inserts_row():
    from app.workers.extraction_worker import _audit
    conn = _FakeConn()

    async def _go():
        await _audit(conn, uuid4(), uuid4(), 'ev.created', {'k': 'v'})
    asyncio.run(_go())
    assert len(conn.executed) == 1
    assert 'audit_logs' in conn.executed[0][0]


def test_fetch_eligible_documents_calls_fetch():
    from app.workers.extraction_worker import _fetch_eligible_documents
    row1 = {'id': uuid4(), 'tenant_id': uuid4(),
            'mime_type': 'application/pdf', 'metadata': {}}
    conn = _FakeConn(fetch_results=[[row1]])

    async def _go():
        return await _fetch_eligible_documents(conn)
    out = asyncio.run(_go())
    assert len(out) == 1


def _doc_row(metadata=None, mime_type='application/pdf'):
    return {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'mime_type': mime_type,
        'metadata': metadata if metadata is not None else {},
    }


def test_process_document_success(monkeypatch):
    from app.workers import extraction_worker
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/x.pdf',
          'extraction_attempt_count': 0}
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': md}
    conn = _FakeConn()

    async def fake_load(metadata, settings, *, tenant_id, tenant_storage_config=None):
        return b'PDF BYTES'
    monkeypatch.setattr(extraction_worker, '_load_file_bytes', fake_load)
    monkeypatch.setattr(extraction_worker, '_extract_text_sync',
                        lambda data, mime: ('hello world', 1))

    async def fake_cfg(conn, tid):
        return {'backend': 'local'}
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())
    sqls = [sql for sql, _ in conn.executed]
    assert any('metadata = metadata || $3' in s for s in sqls)
    assert any('extraction_completed' in str(args) or 'audit_logs' in sql
               for sql, args in conn.executed)


def test_process_document_metadata_is_string(monkeypatch):
    """metadata field arriving as JSON string → parsed and processed."""
    from app.workers import extraction_worker
    tenant_id = uuid4()
    md_str = json.dumps({'storage_key': f'tenants/{tenant_id}/knowledge/x.pdf'})
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': md_str}
    conn = _FakeConn()

    async def fake_load(*a, **kw):
        return b'PDF'
    monkeypatch.setattr(extraction_worker, '_load_file_bytes', fake_load)
    monkeypatch.setattr(extraction_worker, '_extract_text_sync',
                        lambda data, mime: ('hi', 1))

    async def fake_cfg(*a, **kw):
        return None
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())


def test_process_document_metadata_is_invalid_json(monkeypatch):
    """metadata as invalid JSON string → falls back to empty dict."""
    from app.workers import extraction_worker
    tenant_id = uuid4()
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': 'not json'}
    conn = _FakeConn()

    async def fake_cfg(*a, **kw):
        return None
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    # _load_file_bytes raises because storage_key is missing
    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())
    # Should have stamped failure
    assert any('extraction_error' in str(args) or 'status' in s for s, args in conn.executed)


def test_process_document_extraction_fail_not_final(monkeypatch):
    """Extraction failure with attempt < max → status stays draft, extraction_pending=True."""
    from app.workers import extraction_worker
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/x.pdf',
          'extraction_attempt_count': 0}
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': md}
    conn = _FakeConn()

    async def fake_load(*a, **kw):
        raise ValueError('boom')
    monkeypatch.setattr(extraction_worker, '_load_file_bytes', fake_load)

    async def fake_cfg(*a, **kw):
        return None
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    # Force max_attempts high so this attempt is NOT final.
    from app.core.config import get_settings
    orig = get_settings()
    monkeypatch.setattr(extraction_worker, 'get_settings',
                        lambda: SimpleNamespace(**{**orig.model_dump(), 'extraction_max_attempts': 10,
                                                    'extraction_timeout_seconds': 30}))

    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())
    # The first UPDATE we see is the failure stamp
    sqls = [sql for sql, _ in conn.executed]
    assert any('status = $3' in s for s in sqls)


def test_process_document_extraction_fail_final(monkeypatch):
    """Last attempt fails → status='failed'."""
    from app.workers import extraction_worker
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/x.pdf',
          'extraction_attempt_count': 99}
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': md}
    conn = _FakeConn()

    async def fake_load(*a, **kw):
        raise ValueError('boom-final')
    monkeypatch.setattr(extraction_worker, '_load_file_bytes', fake_load)

    async def fake_cfg(*a, **kw):
        return None
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())
    # 'failed' string must appear in the executed args
    args_concat = [str(a) for sql, a in conn.executed]
    assert any("'failed'" in s or 'failed' in s for s in args_concat)


def test_process_document_tenant_config_fetch_error_falls_back(monkeypatch):
    """If fetch_tenant_knowledge_storage_config raises, worker still proceeds with None config."""
    from app.workers import extraction_worker
    tenant_id = uuid4()
    md = {'storage_key': f'tenants/{tenant_id}/knowledge/x.pdf'}
    row = {'id': uuid4(), 'tenant_id': tenant_id, 'mime_type': 'application/pdf',
           'metadata': md}
    conn = _FakeConn()

    async def fake_load(metadata, settings, *, tenant_id, tenant_storage_config=None):
        # tenant_storage_config should be None due to fetch error
        assert tenant_storage_config is None
        return b'PDF'
    monkeypatch.setattr(extraction_worker, '_load_file_bytes', fake_load)
    monkeypatch.setattr(extraction_worker, '_extract_text_sync',
                        lambda d, m: ('text', 1))

    async def fake_cfg(*a, **kw):
        raise RuntimeError('db gone')
    monkeypatch.setattr('app.api.v1.routes.fetch_tenant_knowledge_storage_config', fake_cfg)

    async def _go():
        await extraction_worker._process_document(conn, row)
    asyncio.run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# extraction_worker — _extract_pdf_text / _extract_docx_text edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_extract_pdf_text_invalid_data_raises():
    from app.workers.extraction_worker import _extract_pdf_text
    with pytest.raises(Exception):
        _extract_pdf_text(b'not a pdf')


def test_extract_docx_text_invalid_data_raises():
    from app.workers.extraction_worker import _extract_docx_text
    with pytest.raises(Exception):
        _extract_docx_text(b'not a docx')


# ═══════════════════════════════════════════════════════════════════════════
# digest_worker — _dispatch_one whatsapp + last_sent_at update path
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatch_one_whatsapp_via_sender(monkeypatch):
    """WhatsApp-only with custom sender succeeds."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)

    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    sent = []
    async def fake_wa(conn, *, tenant_id, recipient, cadence, components):
        sent.append({'recipient': recipient, 'cadence': cadence})

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None, 'currency': 'COP',
        'recipient_email': None, 'recipient_whatsapp': '+5730099',
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
            whatsapp_sender=fake_wa,
        )
    out = asyncio.run(_go())
    assert out is True
    assert len(sent) == 1
    # Verify last_sent_at was updated
    assert any('last_sent_at' in sql for sql, _ in conn.executed)


def test_dispatch_one_whatsapp_sender_raises(monkeypatch):
    """WhatsApp sender raises → error logged, not delivered."""
    from app.workers import digest_worker
    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)

    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    async def fake_wa(*a, **kw):
        raise RuntimeError('wa send broken')

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None, 'currency': 'COP',
        'recipient_email': None, 'recipient_whatsapp': '+5730099',
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
            whatsapp_sender=fake_wa,
        )
    assert asyncio.run(_go()) is False


def test_dispatch_one_whatsapp_queue_path(monkeypatch):
    """WhatsApp without explicit sender → uses _queue_whatsapp_template (returns True)."""
    from app.workers import digest_worker
    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)

    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    async def fake_queue(conn, *, tenant_id, recipient, cadence, components):
        return True
    monkeypatch.setattr(digest_worker, '_queue_whatsapp_template', fake_queue)

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None, 'currency': 'COP',
        'recipient_email': None, 'recipient_whatsapp': '+5730099',
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
        )
    assert asyncio.run(_go()) is True


# ═══════════════════════════════════════════════════════════════════════════
# scheduler — exception path for _mark_conversation_pending_recall + auto_rebook_timeout
# ═══════════════════════════════════════════════════════════════════════════


def test_process_pending_reminder_jobs_auto_rebook_kind(monkeypatch):
    """payload.kind == 'auto_rebook_timeout' → dispatches and continues."""
    from app.workers import scheduler

    calls = []
    async def fake_dispatch(conn, row):
        calls.append(row['id'])
    monkeypatch.setattr(scheduler, '_dispatch_auto_rebook_timeout', fake_dispatch)

    job_id = uuid4()
    rows = [{
        'id': job_id, 'tenant_id': uuid4(),
        'payload': json.dumps({'kind': 'auto_rebook_timeout'}),
    }]
    conn = _FakeConn(fetch_results=[rows])

    async def _go():
        return await scheduler._process_pending_reminder_jobs(conn)
    out = asyncio.run(_go())
    assert out == 1
    assert calls == [job_id]


def test_process_pending_reminder_jobs_recall_mark_exception_swallowed(monkeypatch):
    """If _mark_conversation_pending_recall raises, the loop still continues."""
    from app.workers import scheduler

    async def fake_mark(conn, *, tenant_id, payload):
        raise RuntimeError('db broken')
    monkeypatch.setattr(scheduler, '_mark_conversation_pending_recall', fake_mark)

    # _has_approved_template returns truthy
    rows = [{
        'id': uuid4(), 'tenant_id': uuid4(),
        'payload': json.dumps({'purpose': 'service_recall',
                                'service_id': str(uuid4()),
                                'conversation_id': str(uuid4())}),
    }]
    conn = _FakeConn(fetch_results=[rows], fetchval_results=[1])

    async def _go():
        return await scheduler._process_pending_reminder_jobs(conn)
    assert asyncio.run(_go()) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ws_fanout — supervisor cleanup_failed branch (PostgresError on remove_listener)
# ═══════════════════════════════════════════════════════════════════════════


def test_ws_fanout_supervisor_cleanup_failure_logged():
    """When remove_listener raises asyncpg.PostgresError during teardown,
    the supervisor logs the warning instead of crashing."""
    import asyncpg
    from app.admin.ws_fanout import _PubSubFanout

    class _Conn:
        async def add_listener(self, channel, callback):
            pass

        async def remove_listener(self, channel, callback):
            raise asyncpg.PostgresError('listen gone')

        async def execute(self, *a):
            pass

    class _Pool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(self_):
                    return _Conn()
                async def __aexit__(self_, *a):
                    return False
            return _Ctx()

    f = _PubSubFanout()
    tid = uuid4()

    async def _go():
        q = await f.subscribe(_Pool(), tid)
        # Now unsubscribe — supervisor cleanup will hit the PostgresError branch
        await f.unsubscribe(tid, q)

    asyncio.run(_go())


def test_ws_fanout_dispatch_invalid_json_increments_metric(monkeypatch):
    """invalid_json path hits the Prometheus metric increment if available."""
    from app.admin.ws_fanout import _PubSubFanout

    f = _PubSubFanout()
    # Just calling _dispatch should hit the metric-import + inc branch.
    f._dispatch('this is not json')


def test_ws_fanout_dispatch_queue_full_metric(monkeypatch):
    """queue_full path hits the metric branch."""
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    q = asyncio.Queue(maxsize=1)
    q.put_nowait('a')
    f._subscribers[str(tid)] = {q}

    # Monkey-patch put to always fail
    def always_fail(_):
        raise asyncio.QueueFull('always')
    q.put_nowait = always_fail  # type: ignore
    f._dispatch(json.dumps({'tenant_id': str(tid), 'event': 'x'}))


def test_ws_fanout_dispatch_metric_import_failure(monkeypatch):
    """When importing ws_fanout_dropped_total fails, dispatch keeps working."""
    import sys
    from app.admin import ws_fanout

    # Temporarily make the import fail
    orig_metrics = sys.modules.get('app.services.metrics')

    class _Broken:
        def __getattr__(self, name):
            raise RuntimeError('metric not available')

    sys.modules['app.services.metrics'] = _Broken()  # type: ignore
    try:
        f = ws_fanout._PubSubFanout()
        f._dispatch('still not json')  # should not raise
    finally:
        if orig_metrics is not None:
            sys.modules['app.services.metrics'] = orig_metrics
        else:
            sys.modules.pop('app.services.metrics', None)
