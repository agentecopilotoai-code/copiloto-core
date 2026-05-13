"""TASK-0063: end-to-end journey scenarios against an ephemeral PostgreSQL.

These five scenarios cover the high-value paths through the platform:

1. Captación → consentimiento → opt-in → ledger registrado → cita creada.
2. Recordatorio + confirmación activa + no-show.
3. Cancelación self-service por WhatsApp + recall automático en
   ``appointments.completed`` (trigger ``schedule_service_recall_on_completion``).
4. Feedback ≤2★ → handoff + tag "Atención prioritaria" + ``operator_alerts``.
5. Campaña a segmento + atribución de la cita resultante.

The suite is opted in with ``RUN_E2E=1`` and a writable ``TEST_DATABASE_URL``.
Tests outside this file aren't affected: ``conftest_e2e`` fixtures short-circuit
via ``pytest.skip`` when ``RUN_E2E`` is not set.

Each scenario hits the real schema and exercises the service layer directly
(no Meta/Auth0/LLM round-trips). That keeps them deterministic and fast while
still failing on schema or contract regressions (e.g. renaming a column,
dropping the recall trigger, removing the ``operator_alerts`` table, etc.).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest_e2e import (  # noqa: F401 — re-export for pytest discovery
    TenantHandle,
    e2e_enabled,
    run_async,
    tenant_connection,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='set RUN_E2E=1 to run the journey suite'),
]


# ---------------------------------------------------------------------------
# Helper assertions used across scenarios
# ---------------------------------------------------------------------------

async def _consent_ledger_events(conn, tenant_id) -> list[dict]:
    rows = await conn.fetch(
        """
        select event, channel, copy_shown, evidence_payload
        from app.consent_ledger
        where tenant_id=$1
        order by occurred_at asc
        """,
        tenant_id,
    )
    return [dict(r) for r in rows]


async def _outbound_messages(conn, conversation_id) -> list[dict]:
    rows = await conn.fetch(
        """
        select id, message_type, body_text, status, payload
        from app.messages
        where conversation_id=$1 and direction='outbound'
        order by created_at asc
        """,
        conversation_id,
    )
    return [dict(r) for r in rows]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixture-helper tests (criterion: ≥ 3 helpers de fixture probados)
# ---------------------------------------------------------------------------

def test_tenant_factory_seeds_required_records(tenant_factory):
    """The factory must seed every record the journey scenarios depend on."""
    async def run():
        handle: TenantHandle = await tenant_factory(label='helper-seed')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            tenant = await conn.fetchrow(
                'select id, status, vertical_code from app.tenants where id=$1',
                handle.tenant_id,
            )
            assert tenant is not None
            assert tenant['status'] == 'active'

            channel = await conn.fetchrow(
                'select provider, status, account_mode from app.tenant_channels where id=$1',
                handle.channel_id,
            )
            assert channel is not None
            assert channel['provider'] == 'whatsapp_cloud_api'
            assert channel['status'] == 'active'
            assert channel['account_mode'] == 'mock'

            contact = await conn.fetchrow(
                'select opt_in_status from app.contacts where id=$1', handle.contact_id
            )
            assert contact['opt_in_status'] == 'unknown'

            conversation = await conn.fetchrow(
                'select status from app.conversations where id=$1', handle.conversation_id
            )
            assert conversation['status'] == 'open'

            service = await conn.fetchrow(
                'select is_active, name from app.service_catalog where id=$1', handle.service_id
            )
            assert service['is_active'] is True
            assert service['name'].startswith('Servicio ')

    run_async(run())


def test_tenant_factory_isolates_tenants(tenant_factory):
    """Two factories return tenants with distinct IDs and seed independent
    rows. RLS isolation itself is covered by ``test_rls_multitenant_e2e``;
    this fixture's responsibility is to give each scenario fresh state."""
    async def run():
        a = await tenant_factory(label='iso-a')
        b = await tenant_factory(label='iso-b')
        assert a.tenant_id != b.tenant_id
        assert a.channel_id != b.channel_id
        assert a.contact_id != b.contact_id
        assert a.conversation_id != b.conversation_id

        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, a.tenant_id, support_mode=True) as conn:
            # Each tenant has exactly one contact, and the FK was set
            # correctly so a query scoped to tenant A's id only finds A's row.
            count_a = await conn.fetchval(
                'select count(*) from app.contacts where tenant_id=$1', a.tenant_id
            )
            count_b = await conn.fetchval(
                'select count(*) from app.contacts where tenant_id=$1', b.tenant_id
            )
            assert count_a == 1
            assert count_b == 1

    run_async(run())


def test_tenant_connection_sets_rls_context(tenant_factory):
    """``tenant_connection`` must pin ``app.tenant_id`` and ``app.support_mode``."""
    async def run():
        handle = await tenant_factory(label='rls-ctx')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            current = await conn.fetchval('select app.current_tenant_id()')
            support = await conn.fetchval('select app.support_mode()')
            assert current == handle.tenant_id
            assert support is True

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 1: capture → consent → opt-in → first appointment
# ---------------------------------------------------------------------------

def test_scenario_capture_consent_qualification_booking(tenant_factory):
    """Inbound from a brand-new contact triggers the consent template, the
    button reply writes to ``consent_ledger`` and flips ``opt_in_status``, the
    qualification flow then queues the first question on the next
    booking-related inbound, and a follow-up appointment lands with
    ``confirmation_status='pending'``."""
    from app.services.consent import (
        CONSENT_BUTTON_YES,
        CONSENT_REQUEST_BODY,
        enforce_inbound_consent,
    )
    from app.services.qualification_flow import (
        PREFIX_QUALIFY,
        maybe_run_qualification_flow,
    )

    async def run():
        handle = await tenant_factory(label='journey-1')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            conversation = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', handle.contact_id
            ))

            # ── Step 1: first ever inbound from an unknown contact ────────
            first_inbound = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact',
                        'Hola, quiero información', 'text', 'received', '{}'::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
            ))

            decision = await enforce_inbound_consent(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation,
                contact=contact,
                inbound_message=first_inbound,
                business_name='E2E Salon',
            )
            assert decision is not None
            assert decision.handled is True
            assert decision.reason == 'consent_request_sent'

            outbound = await _outbound_messages(conn, handle.conversation_id)
            assert any('Ley 1581' in (m['body_text'] or '') for m in outbound), \
                'consent request body must reference Ley 1581 (regulatory contract)'
            assert any(m['message_type'] == 'interactive' for m in outbound)

            # No ledger entry yet — the contact hasn't accepted.
            assert await _consent_ledger_events(conn, handle.tenant_id) == []

            # ── Step 2: contact taps "Acepto" — opt-in granted ────────────
            contact_after_request = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', handle.contact_id
            ))
            button_reply = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact', 'Acepto', 'interactive',
                        'received', $3::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
                json.dumps({'interactive_id': CONSENT_BUTTON_YES}),
            ))
            decision = await enforce_inbound_consent(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation,
                contact=contact_after_request,
                inbound_message=button_reply,
                business_name='E2E Salon',
            )
            assert decision is not None and decision.reason == 'consent_granted'

            opt_in = await conn.fetchval(
                'select opt_in_status from app.contacts where id=$1', handle.contact_id
            )
            assert opt_in == 'granted'

            ledger = await _consent_ledger_events(conn, handle.tenant_id)
            assert len(ledger) == 1
            assert ledger[0]['event'] == 'granted'
            assert ledger[0]['channel'] == 'whatsapp'
            # The exact text the contact saw must be captured for SIC audits.
            assert CONSENT_REQUEST_BODY.split('{')[0] in (ledger[0]['copy_shown'] or '')

            # ── Step 3: qualification flow kicks off on a booking intent ──
            qualification_qid = await conn.fetchval(
                """
                insert into app.qualification_questions
                  (tenant_id, position, label, key, kind, options, required)
                values ($1, 1, '¿Es tu primera visita?', 'first_visit',
                        'yes_no', '[]'::jsonb, true)
                returning id
                """,
                handle.tenant_id,
            )

            # Refresh conversation so the qualification flow sees the latest
            # metadata (empty self_service/qualification state).
            conversation_after_consent = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            booking_inbound = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact',
                        'Quiero agendar una cita', 'text', 'received', '{}'::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
            ))
            contact_granted = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', handle.contact_id
            ))
            qual_result = await maybe_run_qualification_flow(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation_after_consent,
                contact=contact_granted,
                inbound_message=booking_inbound,
                intent='book_appointment',
            )
            assert qual_result is not None
            assert qual_result['action'] == 'qualification_step_sent', \
                f'expected qualification to start, got {qual_result}'

            # The first qualification question must have been queued outbound
            # as an interactive message that references the question id.
            outbound_after_qual = await _outbound_messages(conn, handle.conversation_id)

            def _payload_str(m):
                raw = m['payload']
                if isinstance(raw, str):
                    return raw
                return json.dumps(raw or {})

            qual_outbound = [
                m for m in outbound_after_qual
                if m['message_type'] == 'interactive' and PREFIX_QUALIFY in _payload_str(m)
            ]
            assert qual_outbound, 'qualification flow must queue an interactive question'
            assert str(qualification_qid) in _payload_str(qual_outbound[-1]), \
                'the queued question payload must reference the question id'

            # ── Step 4: contact provides qualification answer ─────────────
            qual_answer = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact', 'Sí',
                        'interactive', 'received', $3::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
                json.dumps({
                    'interactive_id': f'{PREFIX_QUALIFY}:{qualification_qid}:yes'
                }),
            ))
            conversation_mid_qual = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            answer_result = await maybe_run_qualification_flow(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation_mid_qual,
                contact=contact_granted,
                inbound_message=qual_answer,
                intent='book_appointment',
            )
            assert answer_result is not None
            # Only one question exists, so the flow completes immediately.
            assert answer_result['action'] in {
                'qualification_completed',
                'qualification_step_sent',
            }, f'unexpected qualification answer outcome: {answer_result}'

            # The answer must be persisted in conversation.metadata.qualification
            conversation_after_answer = await conn.fetchrow(
                'select metadata from app.conversations where id=$1',
                handle.conversation_id,
            )
            meta = conversation_after_answer['metadata']
            if isinstance(meta, str):
                meta = json.loads(meta)
            qual_state = meta.get('qualification') or {}
            answered = qual_state.get('answered') or {}
            assert answered.get(str(qualification_qid)) is True, \
                'qualification flow must persist the yes/no answer on the conversation'

            # ── Step 5: a booking lands as scheduled+pending confirmation ─
            starts = _now_utc() + timedelta(days=2)
            appointment_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'scheduled', 'pending')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                starts, starts + timedelta(minutes=30),
            )
            assert appointment_id is not None
            appt = await conn.fetchrow(
                'select status, confirmation_status from app.appointments where id=$1',
                appointment_id,
            )
            assert appt['status'] == 'scheduled'
            assert appt['confirmation_status'] == 'pending'

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 2: reminder → active confirmation → no-show
# ---------------------------------------------------------------------------

def test_scenario_reminder_confirmation_and_noshow(tenant_factory):
    """Active confirmation reply flips the appointment to ``confirmed``; a
    later transition to ``no_show`` is queryable (regression guard for the
    status enum used by analytics + segments)."""
    from app.services.feedback_flow import maybe_record_confirmation

    async def run():
        handle = await tenant_factory(label='journey-2', opt_in_status='granted')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            starts = _now_utc() + timedelta(hours=1)
            appointment_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'scheduled', 'pending')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                starts, starts + timedelta(minutes=30),
            )

            # Reminder job is what the scheduler would have emitted ~24h before.
            await conn.execute(
                """
                insert into app.reminder_jobs
                  (tenant_id, target_type, target_id, channel_id,
                   template_name, payload, scheduled_for)
                values ($1, 'appointment', $2, $3, 'appointment_reminder_24h',
                        $4::jsonb, $5)
                """,
                handle.tenant_id, appointment_id, handle.channel_id,
                json.dumps({'purpose': 'appointment_reminder_24h'}),
                _now_utc() - timedelta(minutes=1),
            )

            # ── Active confirmation "Sí" ──────────────────────────────────
            conversation = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            inbound = {
                'id': uuid.uuid4(),
                'body_text': 'Sí',
                'payload': {},
            }
            result = await maybe_record_confirmation(
                conn,
                tenant_id=handle.tenant_id,
                contact_id=handle.contact_id,
                inbound_message=inbound,
                conversation=conversation,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
            )
            assert result is not None
            assert result['confirmation_status'] == 'confirmed'

            confirmed = await conn.fetchval(
                'select confirmation_status from app.appointments where id=$1',
                appointment_id,
            )
            assert confirmed == 'confirmed'

            # ── No-show transition (client never showed up) ───────────────
            await conn.execute(
                "update app.appointments set status='no_show', updated_at=now() where id=$1",
                appointment_id,
            )
            # Open handoff for the agent so the negative outcome doesn't get lost.
            await conn.execute(
                """
                insert into app.handoffs (tenant_id, conversation_id, reason, status)
                values ($1, $2, 'no_show', 'open')
                """,
                handle.tenant_id, handle.conversation_id,
            )
            counts = await conn.fetchrow(
                """
                select
                  (select count(*) from app.appointments
                     where id=$1 and status='no_show') as no_show_count,
                  (select count(*) from app.handoffs
                     where tenant_id=$2 and conversation_id=$3 and reason='no_show') as handoff_count
                """,
                appointment_id, handle.tenant_id, handle.conversation_id,
            )
            assert counts['no_show_count'] == 1
            assert counts['handoff_count'] == 1

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 3: self-service cancel + service recall
# ---------------------------------------------------------------------------

def test_scenario_self_service_cancel_then_recall(tenant_factory):
    """Cancelling an appointment via WhatsApp transitions it to ``cancelled``,
    and a completed appointment with ``service.recall_interval_days`` set
    auto-creates a ``reminder_jobs`` row via the
    ``schedule_service_recall_on_completion`` trigger."""
    from app.services.appointment_self_service import (
        FLOW_CANCEL,
        INTENT_CANCEL,
        PREFIX_CANCEL_CONFIRM,
        maybe_run_self_service_flow,
    )

    async def run():
        handle = await tenant_factory(label='journey-3', opt_in_status='granted')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            starts = _now_utc() + timedelta(days=3)
            appointment_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'scheduled', 'pending')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                starts, starts + timedelta(minutes=30),
            )

            # Pre-load self-service state mid-flow so the user's button reply
            # routes into the cancellation branch.
            await conn.execute(
                """
                update app.conversations
                set metadata=$1::jsonb, updated_at=now()
                where id=$2
                """,
                json.dumps({
                    'self_service': {
                        'flow': FLOW_CANCEL,
                        'step': 'confirm',
                        'appointment_id': str(appointment_id),
                    }
                }),
                handle.conversation_id,
            )

            conversation = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', handle.contact_id
            ))
            button_reply = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact', 'Sí, cancelar', 'interactive',
                        'received', $3::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
                json.dumps({'interactive_id': f'{PREFIX_CANCEL_CONFIRM}:yes'}),
            ))

            result = await maybe_run_self_service_flow(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation,
                contact=contact,
                inbound_message=button_reply,
                intent=INTENT_CANCEL,
            )
            assert result is not None
            assert result['action'] == 'self_service_cancelled'

            cancelled = await conn.fetchval(
                'select status from app.appointments where id=$1', appointment_id
            )
            assert cancelled == 'cancelled'

            # ── Service recall trigger ────────────────────────────────────
            # A second, finished appointment on a service with a 180-day recall
            # interval should produce a reminder_jobs row at completion.
            await conn.execute(
                'update app.service_catalog set recall_interval_days=180 where id=$1',
                handle.service_id,
            )
            recall_starts = _now_utc() - timedelta(days=1)
            recall_appt_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'scheduled', 'confirmed')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                recall_starts, recall_starts + timedelta(minutes=30),
            )
            await conn.execute(
                "update app.appointments set status='completed' where id=$1",
                recall_appt_id,
            )
            recall_job = await conn.fetchrow(
                """
                select template_name, target_id, payload->>'purpose' as purpose
                from app.reminder_jobs
                where tenant_id=$1 and target_id=$2 and template_name='service_recall'
                """,
                handle.tenant_id, recall_appt_id,
            )
            assert recall_job is not None
            assert recall_job['purpose'] == 'service_recall'

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 4: negative feedback escalation
# ---------------------------------------------------------------------------

def test_scenario_negative_feedback_escalates(tenant_factory):
    """A 1–2★ rating must: (a) persist feedback, (b) flip the conversation to
    ``waiting_agent`` with ``handoff_required=true``, (c) assign the
    ``Atención prioritaria`` tag, (d) insert an ``operator_alerts`` row."""
    from app.services.feedback_flow import maybe_record_feedback

    async def run():
        handle = await tenant_factory(label='journey-4', opt_in_status='granted')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            starts = _now_utc() - timedelta(hours=2)
            appointment_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'completed', 'confirmed')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                starts, starts + timedelta(minutes=30),
            )

            conversation = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            # parse_rating's regex requires the body to be just a digit (with
            # an optional star/slash suffix), so the comment lives in the audit
            # trail only, not in the body the contact sends.
            inbound = {
                'id': uuid.uuid4(),
                'body_text': '1 estrella',
                'payload': {},
            }
            result = await maybe_record_feedback(
                conn,
                tenant_id=handle.tenant_id,
                contact_id=handle.contact_id,
                inbound_message=inbound,
                conversation=conversation,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
            )
            assert result is not None
            assert result['rating'] == 1
            assert result['action'] == 'feedback_negative_escalated'

            feedback_count = await conn.fetchval(
                'select count(*) from app.appointment_feedback where appointment_id=$1',
                appointment_id,
            )
            assert feedback_count == 1

            conversation_state = await conn.fetchrow(
                'select status, handoff_required from app.conversations where id=$1',
                handle.conversation_id,
            )
            assert conversation_state['handoff_required'] is True
            assert conversation_state['status'] == 'waiting_agent'

            open_handoffs = await conn.fetchval(
                """
                select count(*) from app.handoffs
                where tenant_id=$1 and conversation_id=$2 and status='open'
                """,
                handle.tenant_id, handle.conversation_id,
            )
            assert open_handoffs == 1

            tag = await conn.fetchrow(
                """
                select t.name from app.contact_tags t
                join app.contact_tag_assignments a
                  on a.tag_id = t.id and a.contact_id = $1
                where t.tenant_id = $2
                """,
                handle.contact_id, handle.tenant_id,
            )
            assert tag is not None
            assert 'prioritaria' in (tag['name'] or '').lower()

            alert_count = await conn.fetchval(
                """
                select count(*) from app.operator_alerts
                where tenant_id=$1 and kind='negative_feedback'
                """,
                handle.tenant_id,
            )
            assert alert_count == 1

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 5a: booking flow presents the service catalog on book_appointment
# ---------------------------------------------------------------------------

def test_scenario_booking_flow_presents_services(tenant_factory):
    """On a ``book_appointment`` intent for a tenant with an active catalog,
    the booking flow engages, persists the booking state on the conversation
    and queues an outbound message asking the next required step (service
    pick, branch pick or date). This is the bridge between qualification and
    appointment creation."""
    from app.services.booking_flow import maybe_run_booking_flow

    async def run():
        handle = await tenant_factory(label='journey-6', opt_in_status='granted')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            # The resource needs working_hours so the booking flow can later
            # compute slots; the catalog is already populated by tenant_factory.
            await conn.execute(
                """
                update app.resources
                set capabilities=$2::jsonb
                where id=$1
                """,
                handle.resource_id,
                json.dumps({
                    'services': [handle.service_code],
                    'working_hours': {
                        'monday': [{'start': '09:00', 'end': '18:00'}],
                        'tuesday': [{'start': '09:00', 'end': '18:00'}],
                        'wednesday': [{'start': '09:00', 'end': '18:00'}],
                        'thursday': [{'start': '09:00', 'end': '18:00'}],
                        'friday': [{'start': '09:00', 'end': '18:00'}],
                    },
                }),
            )
            # Seed a second active service so the flow has to present the
            # catalog list instead of auto-selecting the only option.
            second_service_id = await conn.fetchval(
                """
                insert into app.service_catalog
                  (tenant_id, name, duration_minutes, is_active,
                   price_amount, price_currency)
                values ($1, 'Servicio alternativo', 45, true, 80000, 'COP')
                returning id
                """,
                handle.tenant_id,
            )

            conversation = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', handle.conversation_id
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', handle.contact_id
            ))
            inbound = dict(await conn.fetchrow(
                """
                insert into app.messages
                  (tenant_id, conversation_id, direction, sender_actor_type,
                   body_text, message_type, status, payload)
                values ($1, $2, 'inbound', 'contact',
                        'Quiero agendar una cita', 'text', 'received', '{}'::jsonb)
                returning *
                """,
                handle.tenant_id, handle.conversation_id,
            ))

            result = await maybe_run_booking_flow(
                conn,
                tenant_id=handle.tenant_id,
                channel_id=handle.channel_id,
                channel_account_mode='mock',
                conversation=conversation,
                contact=contact,
                inbound_message=inbound,
                intent='book_appointment',
                has_catalog=True,
            )
            assert result is not None
            assert result.get('action', '').startswith('booking_'), \
                f'booking flow must engage on book_appointment intent, got {result}'

            # The booking flow must persist its state so a follow-up reply
            # routes back into the same step.
            meta = await conn.fetchval(
                'select metadata from app.conversations where id=$1',
                handle.conversation_id,
            )
            if isinstance(meta, str):
                meta = json.loads(meta)
            booking_state = (meta or {}).get('booking') or {}
            assert booking_state, \
                f'booking_flow must persist state on the conversation, got metadata={meta}'

            # At least one outbound interactive message must have been queued
            # with both service IDs available for selection.
            outbound = await _outbound_messages(conn, handle.conversation_id)

            def _payload_str(m):
                raw = m['payload']
                return raw if isinstance(raw, str) else json.dumps(raw or {})

            interactive_outbound = [
                m for m in outbound if m['message_type'] == 'interactive'
            ]
            assert interactive_outbound, \
                'booking flow must queue at least one interactive prompt'
            combined = ' '.join(_payload_str(m) for m in interactive_outbound)
            assert str(handle.service_id) in combined
            assert str(second_service_id) in combined

    run_async(run())


# ---------------------------------------------------------------------------
# Scenario 5: campaign with attribution
# ---------------------------------------------------------------------------

def test_scenario_campaign_with_attribution(tenant_factory):
    """A campaign targeting a segment can attribute a downstream appointment;
    the ``unique (tenant_id, appointment_id)`` constraint guards against double
    attribution."""
    async def run():
        handle = await tenant_factory(label='journey-5', opt_in_status='granted')
        url = os.environ.get('TEST_DATABASE_URL') or os.environ['DATABASE_URL']
        async with tenant_connection(url, handle.tenant_id, support_mode=True) as conn:
            # An approved campaign-promo template the campaign points to.
            template_id = await conn.fetchval(
                """
                insert into app.whatsapp_templates
                  (tenant_id, channel_id, name, locale, category, status,
                   purpose, components)
                values ($1, $2, 'promo_e2e', 'es', 'marketing', 'approved',
                        'campaign_promo', '{}'::jsonb)
                returning id
                """,
                handle.tenant_id, handle.channel_id,
            )

            segment_id = await conn.fetchval(
                """
                insert into app.contact_segments
                  (tenant_id, name, kind, rules)
                values ($1, 'sin-visita-90d', 'dynamic', $2::jsonb)
                returning id
                """,
                handle.tenant_id,
                json.dumps({'and': [
                    {'field': 'last_appointment_days_ago', 'op': '>', 'value': 90}
                ]}),
            )
            await conn.execute(
                """
                insert into app.contact_segment_members
                  (tenant_id, segment_id, contact_id)
                values ($1, $2, $3)
                """,
                handle.tenant_id, segment_id, handle.contact_id,
            )

            campaign_id = await conn.fetchval(
                """
                insert into app.campaigns
                  (tenant_id, name, status, template_id, segment_filter,
                   attribution_window_days)
                values ($1, 'Reactivación 90d', 'running', $2, $3::jsonb, 14)
                returning id
                """,
                handle.tenant_id, template_id,
                json.dumps({'segment_id': str(segment_id)}),
            )

            # The contact agendó después de la campaña → atribución.
            starts = _now_utc() + timedelta(days=1)
            appointment_id = await conn.fetchval(
                """
                insert into app.appointments
                  (tenant_id, contact_id, conversation_id, service_id,
                   resource_id, service_code, starts_at, ends_at,
                   timezone, status, confirmation_status)
                values ($1, $2, $3, $4, $5, $6, $7, $8,
                        'America/Bogota', 'scheduled', 'pending')
                returning id
                """,
                handle.tenant_id, handle.contact_id, handle.conversation_id,
                handle.service_id, handle.resource_id, handle.service_code,
                starts, starts + timedelta(minutes=30),
            )

            await conn.execute(
                """
                insert into app.campaign_attributions
                  (tenant_id, campaign_id, contact_id, appointment_id)
                values ($1, $2, $3, $4)
                """,
                handle.tenant_id, campaign_id, handle.contact_id, appointment_id,
            )

            attribution = await conn.fetchrow(
                """
                select campaign_id, contact_id, appointment_id
                from app.campaign_attributions
                where tenant_id=$1 and appointment_id=$2
                """,
                handle.tenant_id, appointment_id,
            )
            assert attribution is not None
            assert attribution['campaign_id'] == campaign_id
            assert attribution['contact_id'] == handle.contact_id

            # ── Double-attribution must be rejected by unique constraint ──
            import asyncpg as _asyncpg

            with pytest.raises(_asyncpg.UniqueViolationError):
                await conn.execute(
                    """
                    insert into app.campaign_attributions
                      (tenant_id, campaign_id, contact_id, appointment_id)
                    values ($1, $2, $3, $4)
                    """,
                    handle.tenant_id, campaign_id, handle.contact_id, appointment_id,
                )

    run_async(run())
