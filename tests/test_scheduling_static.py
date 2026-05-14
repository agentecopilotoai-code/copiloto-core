from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))


def test_resource_crud_and_appointment_routes_exist_with_conflict_checks():
    source = API_ROUTES.read_text()

    assert "@tenant_ops_router.get('/resources')" in source
    assert "@tenant_ops_router.post('/resources', status_code=201)" in source
    assert "@tenant_ops_router.patch('/resources/{resource_id}')" in source
    assert "@tenant_ops_router.delete('/resources/{resource_id}', status_code=204)" in source
    assert "async def ensure_resource_available" in source
    assert "tstzrange(starts_at, ends_at, '[)') && tstzrange($3, $4, '[)')" in source
    assert "asyncpg.ExclusionViolationError" in source
    assert "@tenant_ops_router.get('/appointments')" in source
    assert "@tenant_ops_router.patch('/appointments/{appointment_id}')" in source
    assert "@tenant_ops_router.post('/appointments/{appointment_id}/cancel', status_code=202)" in source
    assert "action='appointment.created'" in source
    assert "action='appointment.cancelled'" in source


def test_scheduling_schemas_and_admin_panel_client_are_wired():
    schemas = SCHEMAS.read_text()
    api = CORE_API.read_text()
    component = _operations_desk_source()

    assert 'class ResourceCreate(BaseModel):' in schemas
    assert 'class ResourceUpdate(BaseModel):' in schemas
    assert 'class AppointmentUpdate(BaseModel):' in schemas
    assert 'export function listResources' in api
    assert 'export function createResource' in api
    assert 'export function listAppointments' in api
    assert 'export function createAppointment' in api
    assert 'export function updateAppointment' in api
    assert 'export function cancelAppointment' in api
    assert 'Recursos y agenda' in component
    assert 'handleCreateAppointment' in component
    assert 'handleRescheduleAppointment' in component
    assert 'handleCancelAppointment' in component
