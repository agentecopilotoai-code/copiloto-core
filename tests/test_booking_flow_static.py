from datetime import date
from pathlib import Path

from app.services.booking_flow import (
    PREFIX_DATE,
    PREFIX_RESOURCE,
    PREFIX_SERVICE,
    PREFIX_SLOT,
    STEP_AWAITING_DATE,
    STEP_AWAITING_RESOURCE,
    STEP_AWAITING_SERVICE,
    STEP_AWAITING_SLOT,
    STEP_COMPLETED,
    _hhmm_to_minutes,
    _minutes_to_hhmm,
    _working_hours_for_date,
    compute_free_slots,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
SERVICE_CATALOG = Path('admin-panel/src/components/modules/services/ServiceCatalog.jsx')


def test_compute_free_slots_subtracts_busy_intervals():
    franjas = [{'start': '09:00', 'end': '12:00'}]
    busy = [(10 * 60, 11 * 60)]
    slots = compute_free_slots(franjas, busy, duration_minutes=60)
    starts = [slot['start_time'] for slot in slots]
    assert '09:00' in starts
    assert '11:00' in starts
    assert '10:00' not in starts


def test_compute_free_slots_skips_partial_overlap():
    franjas = [{'start': '09:00', 'end': '13:00'}]
    busy = [(9 * 60 + 30, 10 * 60 + 30)]  # 09:30–10:30
    slots = compute_free_slots(franjas, busy, duration_minutes=60)
    starts = [slot['start_time'] for slot in slots]
    assert '09:00' not in starts  # overlaps with 09:30
    assert '10:00' not in starts  # overlaps with 10:30
    assert '11:00' in starts
    assert '12:00' in starts


def test_compute_free_slots_empty_when_no_franjas():
    assert compute_free_slots([], [], 60) == []


def test_compute_free_slots_handles_multiple_franjas():
    franjas = [
        {'start': '09:00', 'end': '11:00'},
        {'start': '14:00', 'end': '16:00'},
    ]
    slots = compute_free_slots(franjas, [], duration_minutes=60)
    starts = [slot['start_time'] for slot in slots]
    assert starts == ['09:00', '10:00', '14:00', '15:00']


def test_working_hours_reads_target_weekday():
    capabilities = {
        'working_hours': {
            'mon': [{'start': '09:00', 'end': '18:00'}],
            'sat': [],
        }
    }
    monday = date(2026, 5, 11)  # 2026-05-11 is a Monday
    saturday = date(2026, 5, 16)
    assert _working_hours_for_date(capabilities, monday) == [
        {'start': '09:00', 'end': '18:00'}
    ]
    assert _working_hours_for_date(capabilities, saturday) == []


def test_hhmm_helpers_are_inverse():
    for raw in ('09:00', '12:30', '18:45', '00:15'):
        assert _minutes_to_hhmm(_hhmm_to_minutes(raw)) == raw


def test_booking_step_prefixes_are_stable():
    # The orchestrator and bot UI agree on these prefixes to detect each step.
    assert PREFIX_SERVICE == 'book_service'
    assert PREFIX_RESOURCE == 'book_resource'
    assert PREFIX_DATE == 'book_date'
    assert PREFIX_SLOT == 'book_slot'
    assert STEP_AWAITING_SERVICE == 'awaiting_service'
    assert STEP_AWAITING_RESOURCE == 'awaiting_resource'
    assert STEP_AWAITING_DATE == 'awaiting_date'
    assert STEP_AWAITING_SLOT == 'awaiting_slot'
    assert STEP_COMPLETED == 'completed'


def test_schema_adds_service_id_column_to_appointments():
    schema = SCHEMA.read_text()
    assert 'service_id uuid references app.service_catalog(id) on delete set null' in schema
    assert 'fk_appointments_tenant_service foreign key (tenant_id, service_id) references app.service_catalog(tenant_id, id)' in schema


def test_appointment_schema_accepts_service_id():
    schemas_source = SCHEMAS.read_text()
    assert 'service_id: UUID | None = None' in schemas_source
    routes_source = API_ROUTES.read_text()
    assert 'insert into app.appointments (tenant_id, contact_id, conversation_id, service_request_id, service_id, resource_id, service_code, starts_at, ends_at, notes)' in routes_source


def test_availability_endpoints_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_catalog_router.get(\n    '/tenants/{tenant_id}/resources/{resource_id}/availability'\n)" in source
    assert "@tenant_catalog_router.get('/tenants/{tenant_id}/availability')" in source
    assert 'def working_hours_for_date(' in source
    assert 'def compute_free_slots(' in source
    assert 'def fetch_service_duration(' in source
    assert 'def fetch_fallback_duration(' in source
    assert 'service_duration_minutes' in source


def test_orchestrator_hooks_booking_flow_before_rag():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.booking_flow import maybe_run_booking_flow' in source
    assert 'maybe_run_booking_flow(' in source
    assert "message_type'] not in ('text', 'interactive')" in source
    assert 'has_catalog = bool(await conn.fetchval(' in source
    assert "select 1 from app.service_catalog where tenant_id=$1 and is_active=true limit 1" in source


def test_booking_flow_module_exposes_state_machine():
    source = BOOKING_FLOW.read_text()
    assert 'async def maybe_run_booking_flow(' in source
    assert 'build_interactive_button_payload' in source
    assert 'build_interactive_list_payload' in source
    assert 'booking_flow' in source
    assert 'selected_service_id' in source
    assert 'selected_resource_id' in source
    assert 'proposed_date' in source


def test_admin_client_exposes_availability_helpers():
    source = CORE_API.read_text()
    assert 'export function getResourceAvailability' in source
    assert 'export function getTenantAvailability' in source


def test_operations_desk_supports_working_hours_and_calendar():
    source = OPERATIONS_DESK.read_text()
    assert 'WORKING_DAYS' in source
    assert 'workingHoursToJson' in source
    assert 'workingHoursFromCapabilities' in source
    assert 'working-hours-builder' in source
    assert 'weekly-calendar' in source
    assert 'getTenantAvailability' in source
    assert 'handleEditResource' in source


def test_service_catalog_exposes_default_duration_fallback():
    source = SERVICE_CATALOG.read_text()
    assert 'handleSaveDefaultDuration' in source
    assert 'service_durations' in source
    assert 'Duración por defecto' in source
