from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

SCHEMA = Path('infra/postgres/01-schema.sql')
SCHEMAS = Path('app/api/v1/schemas.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
# UI-007.4: the ServiceCatalog monolith was split into a feature directory.
SERVICES_FEATURE = Path('admin-panel/src/features/owner-admin/services')
MODULES = Path('admin-panel/src/app/modules.js')


def _services_feature_source() -> str:
    """Concatenate every JS/JSX file of the services feature so assertions
    survive the UI-007.4 split into table / form / panels / hook."""
    return '\n'.join(
        path.read_text() for path in sorted(SERVICES_FEATURE.rglob('*.js*'))
    )
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))


def test_service_catalog_table_defined_with_rls():
    schema = SCHEMA.read_text()
    assert 'create table app.service_catalog (' in schema
    assert 'tenant_id uuid not null references app.tenants(id) on delete cascade' in schema
    assert 'price_amount numeric(10,2)' in schema
    assert "price_currency char(3) not null default 'COP'" in schema
    assert 'duration_minutes int not null default 60' in schema
    assert 'preparation_notes text' in schema
    assert 'post_service_notes text' in schema
    assert 'is_active boolean not null default true' in schema
    assert 'sort_order int not null default 0' in schema
    assert 'alter table app.service_catalog enable row level security' in schema
    assert "'service_catalog'" in schema
    assert 'trg_service_catalog_touch' in schema
    assert 'uq_service_catalog_tenant_id_id' in schema


def test_service_catalog_endpoints_registered():
    source = routes_aggregated_source()
    assert "tenant_catalog_router = APIRouter(" in source
    assert "@tenant_catalog_router.get('/tenants/{tenant_id}/services')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/services', status_code=201)" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/services/{service_id}')" in source
    assert "@tenant_admin_router.delete('/tenants/{tenant_id}/services/{service_id}', status_code=204)" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/services/reorder')" in source
    assert "action='service_catalog.created'" in source
    assert "action='service_catalog.updated'" in source
    assert "action='service_catalog.deactivated'" in source
    assert "action='service_catalog.reordered'" in source
    assert "router.include_router(tenant_catalog_router)" in source
    assert "require_min_role('admin', allow_service=True)" in source


def test_service_catalog_schemas_and_admin_client_wired():
    schemas = SCHEMAS.read_text()
    api = CORE_API.read_text()
    assert 'class ServiceCreate(BaseModel):' in schemas
    assert 'class ServiceUpdate(BaseModel):' in schemas
    assert 'class ServiceReorderRequest(BaseModel):' in schemas
    assert 'class ServiceReorderItem(BaseModel):' in schemas
    assert 'export function listServices' in api
    assert 'export function createService' in api
    assert 'export function updateService' in api
    assert 'export function deactivateService' in api
    assert 'export function reorderServices' in api


def test_service_catalog_admin_module_exists_and_registered():
    assert SERVICES_FEATURE.is_dir(), 'services feature dir must exist'
    component = _services_feature_source()
    assert 'export function Services' in component
    assert 'listServices' in component
    assert 'createService' in component
    assert 'updateService' in component
    assert 'deactivateService' in component
    assert 'reorderServices' in component

    modules = MODULES.read_text()
    assert "id: 'services'" in modules
    assert 'Servicios' in modules

    layout = ADMIN_LAYOUT.read_text()
    assert "from '../features/owner-admin/services/index.js'" in layout
    assert 'services: {' in layout
    # The legacy module must be fully gone (no parallel implementation).
    assert 'components/modules/services/ServiceCatalog' not in layout


def test_tenant_wizard_renamed_to_negocio_with_free_business_type():
    wizard = _tenant_setup_source()
    assert "label: 'Negocio'" in wizard
    assert 'business_type_label' in wizard
    # The dropdown of fixed verticals must be gone — only free text input remains.
    assert "vertical_code IN ('field_service'" not in wizard
    assert "'field_service'" not in wizard
    assert "'pet_grooming'" not in wizard
