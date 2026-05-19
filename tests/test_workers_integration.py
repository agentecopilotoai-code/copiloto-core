"""Worker integration tests against ephemeral PostgreSQL.

Goal: exercise pure helpers + small worker pieces. We avoid the full
`process_once` loop because the workers use the global `db.pool` singleton
which is bound to a specific asyncio event loop — testing them in isolation
from `TestClient` causes loop conflicts (asyncpg "operation in progress").

The full worker flows are covered indirectly by:
  * `test_journey_e2e.py` (scenario-level)
  * The CI worker boot smoke tests
"""
from __future__ import annotations

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    e2e_http_dsn,
    e2e_http_schema,
)
from tests.conftest_e2e import e2e_enabled

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


# ───── extraction_worker: pure text extraction helpers ────────────────────


def test_extraction_module_imports():
    """Smoke import — the extraction worker only handles binary formats
    (PDF, DOCX) via `_extract_text_sync`; plain text/markdown/csv/json are
    extracted in a different code path. We confirm the helper module loads
    and exposes its public functions."""
    from app.workers import extraction_worker
    assert hasattr(extraction_worker, '_extract_text_sync')
    assert hasattr(extraction_worker, '_extract_pdf_text')
    assert hasattr(extraction_worker, '_extract_docx_text')


def test_extraction_rejects_unknown_mime_type():
    """The helper raises ValueError for MIME types without an extractor —
    that's how the worker reports unsupported uploads."""
    import pytest
    from app.workers.extraction_worker import _extract_text_sync
    with pytest.raises(ValueError, match='No extractor available'):
        _extract_text_sync(b'binary', 'application/octet-stream')


# ───── event_worker: pure helper functions ────────────────────────────────


def test_event_worker_provider_message_id_extracts_wamid():
    from app.workers.event_worker import provider_message_id
    result = {'messages': [{'id': 'wamid.abc123'}]}
    assert provider_message_id(result) == 'wamid.abc123'


def test_event_worker_provider_message_id_returns_none_when_missing():
    from app.workers.event_worker import provider_message_id
    assert provider_message_id({}) is None
    assert provider_message_id({'messages': []}) is None
    assert provider_message_id({'other_field': 'x'}) is None


def test_event_worker_delivery_error_helpers():
    from app.workers.event_worker import delivery_error_code, delivery_error_message
    err = RuntimeError('something broke')
    assert isinstance(delivery_error_message(err), str)
    code = delivery_error_code(err)
    assert isinstance(code, str)
    assert len(code) > 0


# ───── digest_worker: pure helpers ────────────────────────────────────────


def test_digest_worker_wa_id_from_phone_strips_plus():
    from app.workers.digest_worker import _wa_id_from_phone
    assert _wa_id_from_phone('+573001234567') == '573001234567'
    assert _wa_id_from_phone('573001234567') == '573001234567'


# ───── scheduler boot-up helpers ──────────────────────────────────────────


def test_scheduler_module_imports_cleanly():
    """Smoke import — the scheduler module wires several services on import.
    A regression in any of them would crash the worker container at startup."""
    from app.workers import scheduler  # noqa: F401
    # Confirm the module exposes its main loop signature
    assert hasattr(scheduler, 'main')
