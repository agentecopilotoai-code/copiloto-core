"""Static tests for TASK-0062 — Consentimiento doble opt-in + ledger auditable.

Coverage (≥12 tests):
1.  Schema declares ``app.consent_ledger`` with CHECK on event/channel and
    tenant-scoped FK to ``app.contacts``.
2.  Schema installs the append-only trigger that raises SQLSTATE 42501 on
    UPDATE / DELETE attempts.
3.  Schema enables RLS on ``app.consent_ledger`` and registers it in the
    tenant policy loop.
4.  Schema adds ``contacts.consent_version`` for ledger versioning.
5.  ``whatsapp_templates.purpose`` accepts the new ``consent_request`` and
    ``consent_reaffirm`` purposes.
6.  ``enforce_inbound_consent`` queues the consent template + returns
    ``handled=True`` on the first inbound from an unknown contact and does
    NOT write to the ledger yet.
7.  ``enforce_inbound_consent`` writes a ``granted`` ledger row and updates
    ``contacts.opt_in_status`` when the user taps "Acepto".
8.  ``enforce_inbound_consent`` writes a ``revoked`` ledger row + closes
    the conversation when the user taps "No acepto".
9.  ``enforce_inbound_consent`` returns ``None`` when the contact already
    has ``opt_in_status='granted'`` so the orchestrator continues normally.
10. ``enforce_inbound_consent`` skips and returns ``handled=True`` when the
    contact is already revoked / suppressed.
11. ``record_opt_out_by_keyword`` appends a ``revoked`` ledger event with
    the exact words the customer typed.
12. The orchestrator imports the consent service and invokes it before
    intent classification; the opt-out keyword branch also calls
    ``record_opt_out_by_keyword``.
13. ``enqueue_consent_reaffirmations`` inserts reminder_jobs with
    ``payload.purpose='consent_reaffirm'`` only for contacts whose latest
    consent is older than the interval.
14. The scheduler imports + invokes ``enqueue_consent_reaffirmations`` on
    a periodic tick.
15. The admin endpoint ``GET /v1/.../contacts/{contact_id}/consent`` is
    wired and paginates the ledger.
16. ``coreApi.js`` exposes ``listContactConsent`` and the Contacts module
    renders the consent panel.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.services.consent import (
    CONSENT_BUTTON_NO,
    CONSENT_BUTTON_YES,
    CONSENT_REAFFIRM_PURPOSE,
    ConsentDecision,
    enforce_inbound_consent,
    enqueue_consent_reaffirmations,
    record_consent_event,
    record_opt_out_by_keyword,
)
from tests._routes_aggregator import routes_aggregated_source


SCHEMA = Path('infra/postgres/01-schema.sql')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
SCHEDULER = Path('app/workers/scheduler.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
# UI-007.3: the contacts module was split into a feature directory.
CONTACTS_FEATURE = Path('admin-panel/src/features/owner-admin/conversations-contacts')


def _contacts_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(CONTACTS_FEATURE.rglob('*.js*'))
    )


# ─── Fake asyncpg connection ────────────────────────────────────────────────


class _FakeConn:
    """Minimal asyncpg connection that records writes per table."""

    def __init__(self) -> None:
        self.consent_rows: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.domain_events: list[dict[str, Any]] = []
        self.contacts_updates: list[dict[str, Any]] = []
        self.conversation_updates: list[dict[str, Any]] = []
        self.reminder_jobs: list[dict[str, Any]] = []
        # For reaffirmation queries.
        self.contacts_due_for_reaffirm: list[dict[str, Any]] = []

    async def execute(self, sql: str, *args: Any) -> str:
        low = sql.lower().strip()
        if 'update app.contacts' in low:
            self.contacts_updates.append({'sql': sql, 'args': args})
            return 'UPDATE 1'
        if 'update app.conversations' in low:
            self.conversation_updates.append({'sql': sql, 'args': args})
            return 'UPDATE 1'
        if low.startswith('insert into app.domain_events'):
            self.domain_events.append({'args': args})
            return 'INSERT 0 1'
        if low.startswith('insert into app.reminder_jobs'):
            payload = json.loads(args[3]) if len(args) > 3 else {}
            self.reminder_jobs.append({
                'tenant_id': args[0],
                'contact_id': args[1],
                'channel_id': args[2],
                'payload': payload,
            })
            return 'INSERT 0 1'
        return 'SELECT 1'

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        low = sql.lower().strip()
        if low.startswith('insert into app.consent_ledger'):
            (
                tenant_id, contact_id, event, channel,
                legal_basis, purpose, copy_shown, evidence_json, ip, user_agent,
            ) = args
            row = {
                'id': uuid4(),
                'tenant_id': tenant_id,
                'contact_id': contact_id,
                'event': event,
                'channel': channel,
                'legal_basis': legal_basis,
                'purpose': purpose,
                'copy_shown': copy_shown,
                'evidence_payload': json.loads(evidence_json),
                'ip': ip,
                'user_agent': user_agent,
            }
            self.consent_rows.append(row)
            return {'id': row['id']}
        if low.startswith('insert into app.messages'):
            mid = uuid4()
            self.messages.append({
                'id': mid,
                'tenant_id': args[0],
                'conversation_id': args[1],
                'body_text': args[2],
                'message_type': args[3],
                'payload': json.loads(args[4]),
            })
            return {'id': mid}
        return None

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        low = sql.lower()
        if 'from app.contacts c' in low and 'consent_ledger' in low:
            interval_months, limit = args
            return [
                dict(r) for r in self.contacts_due_for_reaffirm[:limit]
            ]
        return []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return 0


# ─── 1–5: Schema ────────────────────────────────────────────────────────────


def test_01_schema_declares_consent_ledger_with_constraints():
    text = SCHEMA.read_text()
    assert 'create table app.consent_ledger' in text
    assert "event in ('granted','revoked','reaffirmed','suppressed')" in text
    assert "channel in ('whatsapp','web','admin','import')" in text
    assert 'fk_consent_ledger_tenant_contact' in text
    assert 'references app.contacts(tenant_id, id) on delete cascade' in text


def test_02_consent_ledger_append_only_trigger_present():
    text = SCHEMA.read_text()
    assert 'consent_ledger_block_mutations' in text
    assert "errcode = '42501'" in text
    assert 'trg_consent_ledger_no_update' in text
    assert 'trg_consent_ledger_no_delete' in text
    # Triggers fire BEFORE update + delete on the ledger table.
    assert 'before update on app.consent_ledger' in text
    assert 'before delete on app.consent_ledger' in text


def test_03_consent_ledger_has_rls_and_policy_loop():
    text = SCHEMA.read_text()
    assert 'alter table app.consent_ledger enable row level security' in text
    # The dynamic policy loop must include the table.
    loop_block = text[text.index("foreach t in array array["):text.index('] loop')]
    assert 'consent_ledger' in loop_block


def test_04_contacts_has_consent_version_column():
    text = SCHEMA.read_text()
    # consent_version vive inline en el CREATE TABLE de app.contacts; no se
    # agrega vía ALTER TABLE incremental (el MVP no está en producción).
    assert 'alter table app.contacts add column consent_version' not in text
    create_block_start = text.index('create table app.contacts')
    create_block_end = text.index(');', create_block_start)
    create_block = text[create_block_start:create_block_end]
    assert re.search(
        r'consent_version int not null default 1', create_block
    )


def test_05_whatsapp_templates_purpose_accepts_consent():
    text = SCHEMA.read_text()
    block = text[text.index('create table app.whatsapp_templates'):]
    block = block[: block.index('create index ix_whatsapp_templates_tenant_purpose')]
    assert "'consent_request'" in block
    assert "'consent_reaffirm'" in block


# ─── 6–10: Consent enforcement runtime ──────────────────────────────────────


def _make_records(opt_in_status: str = 'unknown',
                   interactive_id: str | None = None) -> dict[str, Any]:
    inbound = {
        'id': uuid4(),
        'body_text': '' if interactive_id else 'hola',
        'message_type': 'interactive' if interactive_id else 'text',
        'payload': {'interactive_id': interactive_id} if interactive_id else {},
    }
    return {
        'tenant_id': uuid4(),
        'channel_id': uuid4(),
        'channel_account_mode': 'production',
        'conversation': {'id': uuid4(), 'status': 'open'},
        'contact': {'id': uuid4(), 'opt_in_status': opt_in_status},
        'inbound_message': inbound,
    }


def _run_enforce(conn: _FakeConn, ctx: dict[str, Any]) -> ConsentDecision | None:
    return asyncio.run(
        enforce_inbound_consent(
            conn,
            tenant_id=ctx['tenant_id'],
            channel_id=ctx['channel_id'],
            channel_account_mode=ctx['channel_account_mode'],
            conversation=ctx['conversation'],
            contact=ctx['contact'],
            inbound_message=ctx['inbound_message'],
            business_name='Clinica Demo',
        )
    )


def test_06_first_inbound_unknown_sends_consent_request():
    conn = _FakeConn()
    ctx = _make_records(opt_in_status='unknown')
    decision = _run_enforce(conn, ctx)
    assert isinstance(decision, ConsentDecision)
    assert decision.handled is True
    assert decision.reason == 'consent_request_sent'
    # No ledger row yet ─ ledger only writes on the user's reply.
    assert conn.consent_rows == []
    # Exactly one outbound message of type interactive was queued.
    assert len(conn.messages) == 1
    assert conn.messages[0]['message_type'] == 'interactive'
    assert 'Clinica Demo' in conn.messages[0]['body_text']
    assert any(d for d in conn.domain_events)


def test_07_button_yes_grants_consent_and_writes_ledger():
    conn = _FakeConn()
    ctx = _make_records(opt_in_status='unknown', interactive_id=CONSENT_BUTTON_YES)
    decision = _run_enforce(conn, ctx)
    assert decision.handled is True
    assert decision.reason == 'consent_granted'
    assert len(conn.consent_rows) == 1
    row = conn.consent_rows[0]
    assert row['event'] == 'granted'
    assert row['channel'] == 'whatsapp'
    assert row['copy_shown'].startswith('Hola, somos Clinica Demo')
    # contacts table was updated to granted with opt_in_at=now().
    assert any("opt_in_status='granted'" in u['sql'] for u in conn.contacts_updates)


def test_08_button_no_revokes_and_closes_conversation():
    conn = _FakeConn()
    ctx = _make_records(opt_in_status='unknown', interactive_id=CONSENT_BUTTON_NO)
    decision = _run_enforce(conn, ctx)
    assert decision.handled is True
    assert decision.reason == 'consent_revoked'
    assert conn.consent_rows[0]['event'] == 'revoked'
    assert any("opt_in_status='revoked'" in u['sql'] for u in conn.contacts_updates)
    assert any("status='closed'" in u['sql'] for u in conn.conversation_updates)


def test_09_granted_contact_passes_through():
    conn = _FakeConn()
    ctx = _make_records(opt_in_status='granted')
    decision = _run_enforce(conn, ctx)
    assert decision is None
    assert conn.messages == []
    assert conn.consent_rows == []


def test_10_revoked_contact_is_skipped_no_outbound():
    conn = _FakeConn()
    ctx = _make_records(opt_in_status='revoked')
    decision = _run_enforce(conn, ctx)
    assert decision is not None and decision.handled is True
    assert decision.reason == 'contact_opt_in_revoked'
    assert conn.messages == []
    assert conn.consent_rows == []


# ─── 11–14: Opt-out keyword, orchestrator wiring, reaffirmation ─────────────


def test_11_record_opt_out_by_keyword_appends_revoked_row():
    conn = _FakeConn()
    tenant_id = uuid4()
    contact_id = uuid4()
    inbound = {'id': uuid4(), 'body_text': 'STOP — no me envíes más'}
    asyncio.run(
        record_opt_out_by_keyword(
            conn, tenant_id=tenant_id, contact_id=contact_id, inbound_message=inbound,
        )
    )
    assert len(conn.consent_rows) == 1
    row = conn.consent_rows[0]
    assert row['event'] == 'revoked'
    assert row['copy_shown'] == 'STOP — no me envíes más'
    assert row['evidence_payload']['source'] == 'opt_out_keyword'


def test_12_orchestrator_calls_consent_gate_and_opt_out_ledger():
    text = ORCHESTRATOR.read_text()
    # Consent gate is imported and invoked.
    assert 'from app.services.consent import enforce_inbound_consent, record_opt_out_by_keyword' in text
    assert 'enforce_inbound_consent(' in text
    assert "if consent_decision is not None and consent_decision.handled" in text
    # Opt-out keyword path writes to the ledger.
    assert 'record_opt_out_by_keyword(' in text
    # Legacy bare opt_in skip block was removed.
    assert "if opt_in in ('revoked', 'suppressed')" not in text


def test_13_reaffirm_enqueues_only_due_contacts():
    conn = _FakeConn()
    tenant_id = uuid4()
    contact_id_due = uuid4()
    channel_id = uuid4()
    conn.contacts_due_for_reaffirm = [
        {'tenant_id': tenant_id, 'contact_id': contact_id_due, 'channel_id': channel_id},
    ]
    enqueued = asyncio.run(enqueue_consent_reaffirmations(conn, interval_months=12))
    assert enqueued == 1
    assert len(conn.reminder_jobs) == 1
    job = conn.reminder_jobs[0]
    assert job['payload']['purpose'] == CONSENT_REAFFIRM_PURPOSE
    assert job['payload']['interval_months'] == 12
    assert job['contact_id'] == contact_id_due


def test_14_scheduler_invokes_consent_reaffirmations_periodically():
    text = SCHEDULER.read_text()
    assert 'from app.services.consent import enqueue_consent_reaffirmations' in text
    assert 'enqueue_consent_reaffirmations(' in text
    # Periodic gate present so we don't re-run the SQL every loop.
    assert 'CONSENT_REAFFIRM_EVERY_TICKS' in text


# ─── 15–16: Admin endpoint + Admin Panel tab ────────────────────────────────


def test_15_admin_endpoint_lists_consent_ledger_paginated():
    text = routes_aggregated_source()
    assert "@tenant_ops_router.get('/contacts/{contact_id}/consent')" in text
    assert 'list_contact_consent' in text
    # Reads from consent_ledger with pagination.
    assert 'from app.consent_ledger' in text
    assert 'order by occurred_at desc' in text
    assert 'limit $3 offset $4' in text


def test_16_admin_panel_exposes_consent_tab():
    api = CORE_API.read_text()
    assert 'export function listContactConsent' in api
    assert '/contacts/${contactId}/consent' in api
    ui = _contacts_feature_source()
    assert 'listContactConsent' in ui
    assert 'contact-consent-panel' in ui
    assert 'Consentimiento' in ui


# ─── Extra: ledger write API validations ───────────────────────────────────


def test_17_record_consent_event_rejects_invalid_event_or_channel():
    conn = _FakeConn()
    with pytest.raises(ValueError):
        asyncio.run(
            record_consent_event(
                conn,
                tenant_id=uuid4(),
                contact_id=uuid4(),
                event='unknown',
                channel='whatsapp',
                copy_shown='x',
            )
        )
    with pytest.raises(ValueError):
        asyncio.run(
            record_consent_event(
                conn,
                tenant_id=uuid4(),
                contact_id=uuid4(),
                event='granted',
                channel='sms',
                copy_shown='x',
            )
        )
