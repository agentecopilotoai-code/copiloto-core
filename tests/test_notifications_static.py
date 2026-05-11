import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.services.feedback_flow import parse_confirmation, parse_rating
from app.services.notifications import (
    ALL_NOTIFICATION_PURPOSES,
    DEFAULT_NOTIFICATION_SETTINGS,
    DEFAULT_TEMPLATE_LOCALE,
    PURPOSES_ON_CREATE,
    PURPOSES_POST_APPOINTMENT,
    _scheduled_jobs_for_create,
    _scheduled_jobs_post_appointment,
    build_variables,
    normalize_notification_settings,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
NOTIFICATIONS = Path('app/services/notifications.py')
FEEDBACK = Path('app/services/feedback_flow.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
TENANT_WIZARD = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')


# ───── Pure helpers ─────


def test_default_settings_have_all_required_keys():
    expected_keys = {
        'confirmation_enabled', 'reminder_24h_enabled', 'reminder_1h_enabled',
        'include_location_link', 'location_address', 'location_maps_url',
        'include_preparation_notes',
        'no_show_confirmation_enabled', 'confirmation_reminder_hours',
        'post_instructions_enabled', 'post_instructions_delay_minutes',
        'post_feedback_enabled', 'post_feedback_delay_hours',
        'post_rebooking_enabled', 'post_rebooking_delay_days',
        'post_rebooking_message',
    }
    assert expected_keys.issubset(DEFAULT_NOTIFICATION_SETTINGS.keys())


def test_normalize_notification_settings_merges_with_defaults():
    merged = normalize_notification_settings({'reminder_1h_enabled': True, 'confirmation_reminder_hours': 6})
    assert merged['reminder_1h_enabled'] is True
    assert merged['confirmation_reminder_hours'] == 6
    # Untouched defaults remain.
    assert merged['confirmation_enabled'] is True
    assert merged['post_feedback_enabled'] is True


def test_normalize_notification_settings_handles_string_json():
    merged = normalize_notification_settings(json.dumps({'reminder_1h_enabled': True}))
    assert merged['reminder_1h_enabled'] is True
    assert merged['confirmation_enabled'] is True


def test_scheduled_jobs_for_create_respects_toggles():
    starts_at = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    settings = {
        **DEFAULT_NOTIFICATION_SETTINGS,
        'reminder_1h_enabled': True,
    }
    jobs = _scheduled_jobs_for_create(settings, starts_at)
    purposes = [job['purpose'] for job in jobs]
    assert 'appointment_confirmation' in purposes
    assert 'appointment_reminder_24h' in purposes
    assert 'appointment_reminder_1h' in purposes
    assert 'no_show_confirmation_request' in purposes
    # Scheduled-for offsets line up with the toggles.
    by_purpose = {job['purpose']: job['scheduled_for'] for job in jobs}
    assert by_purpose['appointment_reminder_24h'] == starts_at - timedelta(hours=24)
    assert by_purpose['appointment_reminder_1h'] == starts_at - timedelta(hours=1)
    assert by_purpose['no_show_confirmation_request'] == starts_at - timedelta(
        hours=settings['confirmation_reminder_hours']
    )


def test_scheduled_jobs_for_create_skips_disabled():
    settings = {
        **DEFAULT_NOTIFICATION_SETTINGS,
        'confirmation_enabled': False,
        'reminder_24h_enabled': False,
        'reminder_1h_enabled': False,
        'no_show_confirmation_enabled': False,
    }
    jobs = _scheduled_jobs_for_create(settings, datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc))
    assert jobs == []


def test_scheduled_jobs_post_appointment_uses_configured_delays():
    ends_at = datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc)
    settings = {
        **DEFAULT_NOTIFICATION_SETTINGS,
        'post_rebooking_enabled': True,
        'post_rebooking_delay_days': 14,
    }
    jobs = _scheduled_jobs_post_appointment(settings, ends_at)
    by_purpose = {job['purpose']: job['scheduled_for'] for job in jobs}
    assert by_purpose['post_appointment_instructions'] == ends_at + timedelta(
        minutes=settings['post_instructions_delay_minutes']
    )
    assert by_purpose['post_appointment_feedback'] == ends_at + timedelta(
        hours=settings['post_feedback_delay_hours']
    )
    assert by_purpose['post_appointment_rebooking'] == ends_at + timedelta(days=14)


def test_build_variables_includes_location_only_when_enabled():
    starts_at = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)
    with_loc = build_variables(
        contact_name='María',
        service_name='Manicure',
        resource_name='Ana',
        starts_at=starts_at,
        address='Cra 7 #45',
        maps_url='https://maps.example/x',
        preparation_notes='Llega 10 min antes',
        include_location=True,
        include_preparation=True,
    )
    assert with_loc['1'] == 'María'
    assert with_loc['2'] == 'Manicure'
    assert with_loc['3'] == starts_at.strftime('%d/%m/%Y')
    assert with_loc['4'] == starts_at.strftime('%H:%M')
    assert with_loc['5'] == 'Ana'
    assert with_loc['6'] == 'Cra 7 #45'
    assert with_loc['7'] == 'https://maps.example/x'
    # preparation_notes lands in the next slot (8).
    assert with_loc['8'] == 'Llega 10 min antes'

    no_loc = build_variables(
        contact_name='María',
        service_name='Manicure',
        resource_name='Ana',
        starts_at=starts_at,
        address='Cra 7 #45',
        maps_url='https://maps.example/x',
        preparation_notes='Llega 10 min antes',
        include_location=False,
        include_preparation=False,
    )
    assert '6' not in no_loc
    assert '7' not in no_loc


def test_default_template_locale_is_es():
    assert DEFAULT_TEMPLATE_LOCALE == 'es'


def test_all_purposes_are_covered():
    assert set(PURPOSES_ON_CREATE).issubset(set(ALL_NOTIFICATION_PURPOSES))
    assert set(PURPOSES_POST_APPOINTMENT).issubset(set(ALL_NOTIFICATION_PURPOSES))


# ───── feedback_flow ─────


def test_parse_rating_accepts_integers_one_to_five():
    for value in ('1', '2', ' 3 ', '4⭐', '5 estrellas'):
        assert parse_rating(value) is not None
    assert parse_rating('0') is None
    assert parse_rating('6') is None
    assert parse_rating('uno') is None
    assert parse_rating('') is None
    assert parse_rating(None) is None


def test_parse_confirmation_detects_si_and_no():
    assert parse_confirmation('Sí, confirmo mi cita') == 'confirmed'
    assert parse_confirmation('confirmo') == 'confirmed'
    assert parse_confirmation('si') == 'confirmed'
    assert parse_confirmation('No puedo asistir') == 'declined'
    assert parse_confirmation('Necesito cancelar') == 'declined'
    assert parse_confirmation('quiero reagendar') == 'declined'
    assert parse_confirmation('') is None
    assert parse_confirmation('mejor mañana') is None
    assert parse_confirmation(None) is None


# ───── Functional: helper inserts reminder jobs against a FakeConn ─────


class FakeConn:
    def __init__(self, appointment, settings):
        self.appointment = appointment
        self.settings = settings
        self.inserted_jobs = []
        self.cancelled_count = 0

    async def fetchval(self, query, *args):
        if 'tenant_settings' in query and 'notification_settings' in query:
            return self.settings
        if 'tenant_channels' in query:
            return self.appointment['channel_id']
        return None

    async def fetchrow(self, query, *args):
        if 'from app.appointments a' in query:
            return self.appointment
        if 'insert into app.reminder_jobs' in query:
            job_id = uuid4()
            tenant_id, target_id, channel_id, template_name, locale, payload, scheduled_for = args
            self.inserted_jobs.append({
                'id': job_id,
                'tenant_id': tenant_id,
                'target_id': target_id,
                'channel_id': channel_id,
                'template_name': template_name,
                'template_locale': locale,
                'payload': json.loads(payload) if isinstance(payload, str) else payload,
                'scheduled_for': scheduled_for,
            })
            return {'id': job_id}
        return None

    async def fetch(self, query, *args):
        if 'update app.reminder_jobs' in query and "status='cancelled'" in query:
            cancelled = [job for job in self.inserted_jobs if job['target_id'] == args[1]]
            self.cancelled_count += len(cancelled)
            return [{'id': job['id']} for job in cancelled]
        return []

    async def execute(self, *_args, **_kwargs):
        return None


def _build_appointment(channel_id):
    starts = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
    return {
        'id': uuid4(),
        'starts_at': starts,
        'ends_at': starts + timedelta(hours=1),
        'conversation_id': uuid4(),
        'service_id': uuid4(),
        'resource_id': uuid4(),
        'contact_id': uuid4(),
        'contact_name': 'María',
        'channel_id': channel_id,
        'service_name': 'Manicure',
        'preparation_notes': 'Llega 10 min antes',
        'resource_name': 'Ana',
    }


def test_create_reminder_jobs_persists_purpose_and_variables():
    from app.services.notifications import create_appointment_reminder_jobs

    channel_id = uuid4()
    tenant_id = uuid4()
    appointment = _build_appointment(channel_id)
    settings = {
        **DEFAULT_NOTIFICATION_SETTINGS,
        'location_address': 'Cra 7 #45',
        'location_maps_url': 'https://maps.example/x',
    }
    conn = FakeConn(appointment, json.dumps(settings))

    result = asyncio.run(create_appointment_reminder_jobs(conn, tenant_id, appointment['id']))

    assert result['created'] == len(conn.inserted_jobs)
    # Confirmation, reminder_24h, no_show_confirmation_request,
    # post_instructions and post_feedback are enabled by default.
    purposes = [job['payload']['purpose'] for job in conn.inserted_jobs]
    assert purposes.count('appointment_confirmation') == 1
    assert purposes.count('appointment_reminder_24h') == 1
    assert purposes.count('no_show_confirmation_request') == 1
    assert purposes.count('post_appointment_instructions') == 1
    assert purposes.count('post_appointment_feedback') == 1
    assert all(job['payload']['appointment_id'] == str(appointment['id']) for job in conn.inserted_jobs)
    # Variables contain ordered keys 1..5 plus location and preparation.
    first = conn.inserted_jobs[0]['payload']['variables']
    assert first['1'] == 'María'
    assert first['2'] == 'Manicure'
    assert first['3'] == appointment['starts_at'].strftime('%d/%m/%Y')


def test_cancel_reminder_jobs_marks_pending_as_cancelled():
    from app.services.notifications import cancel_appointment_reminder_jobs

    channel_id = uuid4()
    tenant_id = uuid4()
    appointment = _build_appointment(channel_id)
    conn = FakeConn(appointment, json.dumps(DEFAULT_NOTIFICATION_SETTINGS))
    # First create jobs, then cancel.
    from app.services.notifications import create_appointment_reminder_jobs
    asyncio.run(create_appointment_reminder_jobs(conn, tenant_id, appointment['id']))

    count = asyncio.run(cancel_appointment_reminder_jobs(conn, tenant_id, appointment['id']))
    assert count == len(conn.inserted_jobs)


# ───── Static surface checks ─────


def test_schema_adds_notification_settings_and_feedback_table():
    schema = SCHEMA.read_text()
    assert "notification_settings jsonb not null default '{}'::jsonb" in schema
    assert 'create table app.appointment_feedback (' in schema
    assert 'rating int not null check (rating between 1 and 5)' in schema
    assert "'appointment_feedback'" in schema
    assert 'alter table app.appointment_feedback enable row level security' in schema
    assert 'uq_appointment_feedback_tenant_id_id' in schema


def test_routes_call_notifications_on_appointment_lifecycle():
    source = API_ROUTES.read_text()
    assert 'from app.services.notifications import' in source
    assert 'create_appointment_reminder_jobs' in source
    assert 'cancel_appointment_reminder_jobs' in source
    assert 'regenerate_appointment_reminder_jobs' in source
    assert "@tenant_ops_router.post('/appointments/{appointment_id}/feedback', status_code=201)" in source
    assert "@tenant_ops_router.get('/appointments/{appointment_id}/feedback')" in source
    assert 'rating must be an integer 1-5' in source
    assert "action='appointment.feedback_recorded'" in source


def test_tenant_settings_patch_persists_notification_settings():
    source = API_ROUTES.read_text()
    assert "'notification_settings'" in source
    assert "notification_settings=$7::jsonb" in source


def test_orchestrator_runs_feedback_and_confirmation_flows():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.feedback_flow import' in source
    assert 'maybe_record_feedback' in source
    assert 'maybe_record_confirmation' in source


def test_booking_flow_creates_reminder_jobs_after_appointment():
    source = BOOKING_FLOW.read_text()
    assert 'from app.services.notifications import create_appointment_reminder_jobs' in source
    assert 'create_appointment_reminder_jobs(conn, tenant_id, appointment[' in source


def test_notifications_module_exposes_public_api():
    source = NOTIFICATIONS.read_text()
    assert 'DEFAULT_NOTIFICATION_SETTINGS' in source
    assert 'async def create_appointment_reminder_jobs(' in source
    assert 'async def cancel_appointment_reminder_jobs(' in source
    assert 'async def regenerate_appointment_reminder_jobs(' in source
    assert 'def build_variables(' in source


def test_feedback_flow_exposes_helpers():
    source = FEEDBACK.read_text()
    assert 'def parse_rating(' in source
    assert 'def parse_confirmation(' in source
    assert 'async def maybe_record_feedback(' in source
    assert 'async def maybe_record_confirmation(' in source


def test_admin_client_exposes_feedback_helpers():
    source = CORE_API.read_text()
    assert 'export function listAppointmentFeedback' in source
    assert 'export function createAppointmentFeedback' in source


def test_tenant_wizard_has_notificaciones_tab():
    source = TENANT_WIZARD.read_text()
    assert "id: 'notificaciones'" in source
    assert "label: 'Notificaciones'" in source
    assert 'DEFAULT_NOTIFICATION_SETTINGS' in source
    assert 'notification_settings: notificationSettings' in source
    assert 'confirmation_reminder_hours' in source
    assert 'post_rebooking_message' in source


def test_operations_desk_renders_confirmation_and_rating_badges():
    source = OPERATIONS_DESK.read_text()
    assert 'appointment-badges' in source
    assert 'confirmation-' in source
    assert 'feedback-rating' in source
    assert 'listAppointmentFeedback' in source
