from pathlib import Path

SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
CONTACTS_MODULE = Path('admin-panel/src/components/modules/contacts/ContactsModule.jsx')
MODULES = Path('admin-panel/src/data/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
TENANT_WIZARD = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')


def test_contact_tags_tables_defined_with_rls():
    schema = SCHEMA.read_text()
    assert 'create table app.contact_tags (' in schema
    assert 'tenant_id uuid not null references app.tenants(id) on delete cascade' in schema
    assert 'unique (tenant_id, name)' in schema
    assert 'color varchar(7)' in schema
    assert 'create table app.contact_tag_assignments (' in schema
    assert 'primary key (contact_id, tag_id)' in schema
    assert 'assigned_by uuid references app.users(id)' in schema
    assert 'create table app.contact_notes (' in schema
    assert 'body text not null' in schema
    assert 'created_by uuid references app.users(id)' in schema
    assert 'alter table app.contact_tags enable row level security' in schema
    assert 'alter table app.contact_tag_assignments enable row level security' in schema
    assert 'alter table app.contact_notes enable row level security' in schema
    assert "'contact_tags','contact_tag_assignments','contact_notes'" in schema
    assert 'trg_contact_tags_touch' in schema
    assert 'trg_contact_notes_touch' in schema
    assert 'uq_contact_tags_tenant_id_id' in schema
    assert 'uq_contact_notes_tenant_id_id' in schema
    assert 'fk_contact_tag_assignments_tenant_contact' in schema
    assert 'fk_contact_tag_assignments_tenant_tag' in schema
    assert 'fk_contact_notes_tenant_contact' in schema


def test_contact_crm_endpoints_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_ops_router.get('/tenants/{tenant_id}/contact-tags')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/contact-tags', status_code=201)" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/contact-tags/{tag_id}')" in source
    assert "@tenant_admin_router.delete('/tenants/{tenant_id}/contact-tags/{tag_id}', status_code=204)" in source
    assert "@tenant_ops_router.post('/contacts/{contact_id}/tags'" in source
    assert "@tenant_ops_router.delete('/contacts/{contact_id}/tags/{tag_id}'" in source
    assert "@tenant_ops_router.post('/contacts/{contact_id}/notes'" in source
    assert "@tenant_ops_router.get('/contacts/{contact_id}/notes')" in source
    assert "@tenant_ops_router.get('/contacts/{contact_id}/profile')" in source
    assert "@tenant_ops_router.get('/contacts')" in source
    assert "action='contact_tag.created'" in source
    assert "action='contact_tag.updated'" in source
    assert "action='contact_tag.deleted'" in source
    assert "action='contact_tag.assigned'" in source
    assert "action='contact_tag.unassigned'" in source
    assert "action='contact_note.created'" in source


def test_contact_crm_schemas_defined():
    schemas = SCHEMAS.read_text()
    assert 'class ContactTagCreate(BaseModel):' in schemas
    assert 'class ContactTagUpdate(BaseModel):' in schemas
    assert 'class ContactTagAssign(BaseModel):' in schemas
    assert 'class ContactNoteCreate(BaseModel):' in schemas


def test_inbox_includes_contact_tags():
    source = API_ROUTES.read_text()
    # The conversations list endpoint enriches each item with the contact's tags.
    assert "conversation['contact_tags']" in source
    assert "from app.contact_tag_assignments cta" in source


def test_contact_profile_returns_full_history():
    source = API_ROUTES.read_text()
    assert 'get_contact_profile' in source
    assert "from app.appointments" in source
    assert "from app.contact_notes n" in source
    assert "from app.conversations c" in source
    assert "'first_visit_at'" in source
    assert "'last_visit_at'" in source
    assert "'average_rating'" in source


def test_core_api_exposes_contact_crm_helpers():
    api = CORE_API.read_text()
    assert 'export function listContactTags' in api
    assert 'export function createContactTag' in api
    assert 'export function updateContactTag' in api
    assert 'export function deleteContactTag' in api
    assert 'export function listContacts' in api
    assert 'export function getContactProfile' in api
    assert 'export function assignContactTags' in api
    assert 'export function unassignContactTag' in api
    assert 'export function listContactNotes' in api
    assert 'export function createContactNote' in api


def test_contacts_module_exists_and_registered():
    assert CONTACTS_MODULE.exists(), 'ContactsModule.jsx must exist'
    component = CONTACTS_MODULE.read_text()
    assert 'export function ContactsModule' in component
    assert 'listContacts' in component
    assert 'getContactProfile' in component
    assert 'createContactNote' in component
    assert 'assignContactTags' in component
    assert 'unassignContactTag' in component

    modules = MODULES.read_text()
    assert "id: 'contacts'" in modules
    assert 'Contactos' in modules

    layout = ADMIN_LAYOUT.read_text()
    assert 'ContactsModule' in layout
    assert "activeModuleId === 'contacts'" in layout


def test_tenant_wizard_manages_contact_tags():
    wizard = TENANT_WIZARD.read_text()
    assert 'listContactTags' in wizard
    assert 'createContactTag' in wizard
    assert 'updateContactTag' in wizard
    assert 'deleteContactTag' in wizard
    assert 'Etiquetas de contacto' in wizard


def test_operations_desk_shows_and_manages_tags():
    desk = OPERATIONS_DESK.read_text()
    assert 'listContactTags' in desk
    assert 'assignContactTags' in desk
    assert 'unassignContactTag' in desk
    assert 'createContactNote' in desk
    assert 'contact_tags' in desk
