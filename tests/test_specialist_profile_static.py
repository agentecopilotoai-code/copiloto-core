"""Static tests for TASK-0049 — Specialist profile (bio/photo/specialty) in booking.

Coverage:
- Schema additions for ``app.resources`` (bio, photo_media_asset_id, specialty,
  license_number, years_of_experience, public_profile) and the tenant-scoped
  FK against ``media_assets``.
- Admin CRUD routes accept and persist the new fields; PATCH emits the
  ``resource.profile_updated`` audit when profile fields change.
- Public ``GET /v1/tenants/{tenant_id}/resources/public`` is registered on the
  unauthenticated public router and only surfaces public-flagged resources.
- Booking flow sends an image+caption message before the resource list and a
  text-only message when no photo media is attached.
- Pydantic schemas expose the new fields with the right validators.
- Admin panel ResourcesPanel (rendered inside OperationsDesk) registers inputs
  for the new fields and the Media Library selector.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import ResourceCreate, ResourceUpdate
from app.services import booking_flow

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
OPERATIONS_DESK = Path(
    'admin-panel/src/components/modules/operations/OperationsDesk.jsx'
)


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_extends_resources_with_specialist_columns():
    schema = SCHEMA.read_text()
    assert 'bio text' in schema
    assert 'photo_media_asset_id uuid' in schema
    assert 'specialty text' in schema
    assert 'license_number text' in schema
    assert (
        'years_of_experience int check (years_of_experience is null '
        'or years_of_experience >= 0)'
    ) in schema
    assert 'public_profile boolean not null default true' in schema


def test_schema_adds_tenant_scoped_fk_to_media_assets():
    schema = SCHEMA.read_text()
    assert 'fk_resources_tenant_photo' in schema
    assert (
        'foreign key (tenant_id, photo_media_asset_id) references '
        'app.media_assets(tenant_id, id)'
    ) in schema


def test_schema_creates_public_profile_index():
    schema = SCHEMA.read_text()
    assert (
        'create index ix_resources_public on app.resources(tenant_id, '
        'public_profile, is_active)'
    ) in schema


# ───── Pydantic schemas ────────────────────────────────────────────────────


def test_resource_create_exposes_profile_fields():
    fields = ResourceCreate.model_fields
    assert 'bio' in fields
    assert 'photo_media_asset_id' in fields
    assert 'specialty' in fields
    assert 'license_number' in fields
    assert 'years_of_experience' in fields
    assert 'public_profile' in fields
    # Defaults: public_profile starts true; bio and friends are optional.
    assert fields['public_profile'].default is True


def test_resource_update_accepts_partial_profile_changes():
    fields = ResourceUpdate.model_fields
    for key in (
        'bio',
        'photo_media_asset_id',
        'specialty',
        'license_number',
        'years_of_experience',
        'public_profile',
    ):
        assert key in fields
    # public_profile is nullable on update so callers can leave it untouched.
    assert fields['public_profile'].default is None


# ───── Routes ──────────────────────────────────────────────────────────────


def test_public_resources_endpoint_registered_without_auth():
    public_router = routes_module.public_router
    routes = [r for r in public_router.routes if hasattr(r, 'path')]
    paths = {(getattr(r, 'path', ''), tuple(sorted(getattr(r, 'methods', []) or []))) for r in routes}
    target = ('/tenants/{tenant_id}/resources/public', ('GET',))
    assert target in paths


def test_public_endpoint_filters_public_profile_and_active():
    source = ROUTES.read_text()
    # The handler restricts the query to active+public rows and joins media.
    assert 'and r.is_active = true' in source
    assert 'and r.public_profile = true' in source
    assert 'left join app.media_assets m' in source
    assert 'photo_url' in source


def test_resource_create_persists_profile_fields():
    source = ROUTES.read_text()
    assert 'bio, photo_media_asset_id, specialty, license_number, years_of_experience' in source
    assert 'public_profile, is_active' in source
    assert 'payload.public_profile' in source
    assert 'payload.photo_media_asset_id' in source


def test_resource_update_emits_profile_updated_audit():
    source = ROUTES.read_text()
    assert "action='resource.profile_updated'" in source
    assert 'profile_changed' in source


# ───── Booking flow ────────────────────────────────────────────────────────


def test_list_active_resources_pulls_specialist_profile_columns():
    source = inspect.getsource(booking_flow._list_active_resources)
    assert 'r.bio' in source
    assert 'r.specialty' in source
    assert 'r.photo_media_asset_id' in source
    assert 'r.public_profile=true' in source
    assert 'left join app.media_assets m' in source


def test_specialist_caption_truncates_to_140_chars():
    long_bio = 'x' * 500
    text = booking_flow._specialist_caption({
        'name': 'Dra. Pérez',
        'specialty': 'Odontología',
        'bio': long_bio,
    })
    assert len(text) <= 140
    assert text.startswith('Dra. Pérez • Odontología')


def test_specialist_caption_omits_specialty_when_missing():
    text = booking_flow._specialist_caption({'name': 'Carlos', 'specialty': '', 'bio': ''})
    assert text == 'Carlos'


def test_present_resources_sends_specialist_photo_before_list():
    source = inspect.getsource(booking_flow._present_resources)
    assert '_queue_specialist_photo' in source
    # Both branches (one resource and multiple) call the helper.
    assert source.count('_queue_specialist_photo') >= 2


def test_queue_specialist_photo_falls_back_to_text_without_photo():
    source = inspect.getsource(booking_flow._queue_specialist_photo)
    assert "message_type = 'text'" in source
    assert "if photo_uri and photo_kind == 'image':" in source
    assert "message_type = 'image'" in source


# ───── Admin panel ─────────────────────────────────────────────────────────


def test_operations_desk_registers_specialist_profile_inputs():
    source = OPERATIONS_DESK.read_text()
    assert 'specialist-profile-fields' in source
    assert 'Perfil público del especialista' in source
    assert 'resourceForm.bio' in source
    assert 'resourceForm.specialty' in source
    assert 'resourceForm.licenseNumber' in source
    assert 'resourceForm.yearsOfExperience' in source
    assert 'resourceForm.publicProfile' in source
    assert 'resourceForm.photoMediaAssetId' in source
    assert 'listMediaAssets' in source
    assert "kind: 'image'" in source
