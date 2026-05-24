"""Static checks para TASK-INFLU-010 — face variations async."""
from __future__ import annotations

from pathlib import Path

from app.influencer.face_variations_router import (
    _build_prompt,
    face_variations_router,
)


ROUTER_SRC = Path('app/influencer/face_variations_router.py').read_text(encoding='utf-8')
SCHEMA_SRC = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


def test_post_returns_201_synchronous():
    """UI-INFLU-014.3: el endpoint ahora es SÍNCRONO — devuelve 201
    Created con assets pobladas (no 202 Accepted con polling)."""
    for route in face_variations_router.routes:
        if route.path.endswith('/variations') and 'POST' in route.methods:
            assert route.status_code == 201
            return
    raise AssertionError('POST /variations no encontrado')


def test_get_status_endpoint_registered():
    paths = {r.path for r in face_variations_router.routes}
    assert '/v1/influencer/personas/{persona_id}/face/variations/{variation_request_id}' in paths


def test_prompt_includes_face_traits():
    face = {
        'ethnicity': 'latin', 'eye_color': 'brown', 'hair_color': 'black',
        'hair_style': 'long', 'skin_tone': 'medium', 'age_range': '25-34',
    }
    prompt = _build_prompt(face)
    assert 'latin' in prompt
    assert 'brown' in prompt and 'eyes' in prompt
    assert 'black' in prompt and 'long' in prompt
    assert 'medium' in prompt
    assert '25-34' in prompt
    assert 'consistent identity' in prompt


def test_prompt_handles_empty_face():
    """Si face={} (paso 1 sin completar), devolver prompt genérico."""
    prompt = _build_prompt({})
    assert prompt
    assert 'portrait headshot' in prompt


# ─── UI-INFLU-014.1 — prompt builder usa todos los jsonb del wizard ────────


def test_prompt_includes_body_traits():
    """El builder debe agregar silhouette/posture/height del jsonb body."""
    prompt = _build_prompt(
        face={'ethnicity': 'latin'},
        body={'silhouette': 'athletic', 'posture': 'confident', 'height_cm': 170},
    )
    assert 'athletic build' in prompt
    assert 'confident posture' in prompt
    assert '170cm' in prompt


def test_prompt_includes_identity_setting_and_categories():
    """El builder incluye city/country como setting visual + categories."""
    prompt = _build_prompt(
        face={'ethnicity': 'latin'},
        identity={
            'city': 'Cartagena', 'country': 'Colombia',
            'categories': ['fashion', 'travel', 'lifestyle', 'extra-cap'],
        },
    )
    assert 'Cartagena Colombia setting' in prompt
    # Limita a 3 categorías para no saturar el prompt.
    assert 'fashion' in prompt and 'travel' in prompt and 'lifestyle' in prompt
    assert 'extra-cap' not in prompt


def test_prompt_includes_voice_tone_as_expression():
    """El tono de voz se usa como pista de expresión facial."""
    prompt = _build_prompt(
        face={'ethnicity': 'latin'},
        voice={'tone': 'warm'},
    )
    assert 'warm expression' in prompt


def test_prompt_partial_progression_works():
    """El usuario puede pedir generar desde cualquier step — los jsonb
    posteriores al actual están vacíos y el builder los omite sin errores."""
    # Solo face → no debe incluir body/identity/voice (no agrega ruido)
    prompt = _build_prompt(face={'ethnicity': 'latin', 'eye_color': 'brown'})
    assert 'build' not in prompt
    assert 'posture' not in prompt
    assert 'setting' not in prompt
    assert 'expression' not in prompt


def test_prompt_handles_none_inputs_safely():
    """None en cualquier slot no debe romper el builder."""
    prompt = _build_prompt(face=None, body=None, identity=None, voice=None)
    assert prompt
    assert 'portrait headshot' in prompt
    assert 'consistent identity' in prompt


def test_prompt_handles_country_only_setting():
    """Si hay country pero no city, igual incluye el setting."""
    prompt = _build_prompt(
        face={'ethnicity': 'latin'},
        identity={'country': 'Colombia'},
    )
    assert 'Colombia setting' in prompt


def test_prompt_omits_private_identity_fields():
    """Name/handle/age numérico son metadata, NO deben filtrarse al prompt
    visual del image provider."""
    prompt = _build_prompt(
        face={'ethnicity': 'latin'},
        identity={
            'name': 'Sofía Vega', 'handle': 'sofia_vega', 'age': 27,
            'description': 'INTERNAL NOTES NEVER SEND',
        },
    )
    assert 'Sofía Vega' not in prompt
    assert 'sofia_vega' not in prompt
    assert 'INTERNAL' not in prompt
    assert '27' not in prompt


def test_variation_request_count_defaults_to_one():
    """UI-INFLU-014.1: cada click genera 1 variación (=1 crédito)."""
    from app.influencer.face_variations_router import VariationRequest
    req = VariationRequest()
    assert req.count == 1
    # Y sigue aceptando override hasta 10 para herramientas internas.
    assert VariationRequest(count=10).count == 10


def test_variation_request_response_has_assets_field():
    """UI-INFLU-014.1: la response debe incluir lista de assets para que
    el frontend haga polling y muestre las thumbnails generadas."""
    from app.influencer.face_variations_router import (
        VariationAsset,
        VariationRequestResponse,
    )
    from uuid import uuid4
    resp = VariationRequestResponse(
        id=uuid4(), persona_id=uuid4(), requested_count=1, status='queued',
    )
    assert resp.assets == []  # default empty
    # Cuando completa, los assets vienen poblados.
    asset = VariationAsset(
        id=uuid4(), storage_key='tenants/x/y/0', url='/admin/api/core/v1/influencer/storage/tenants/x/y/0',
        mime='image/png', width=1024, height=1024,
    )
    resp_done = VariationRequestResponse(
        id=uuid4(), persona_id=uuid4(), requested_count=1, status='completed',
        assets=[asset],
    )
    assert len(resp_done.assets) == 1
    assert resp_done.assets[0].url.endswith('/0')


def test_storage_key_to_url_passthrough_http():
    """URLs ya absolutas no se modifican."""
    from app.influencer.face_variations_router import _storage_key_to_url
    assert _storage_key_to_url('https://cdn.example/x.png') == 'https://cdn.example/x.png'
    assert _storage_key_to_url('http://localhost/x.png') == 'http://localhost/x.png'


def test_storage_router_mounted_in_main():
    """UI-INFLU-014.7: el storage_router debe estar registrado en main.py
    para servir GET /v1/influencer/storage/{key:path}."""
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'storage_router as influencer_storage_router' in main_src
    assert 'include_router(influencer_storage_router)' in main_src


def test_storage_key_belongs_to_tenant():
    """Regla de seguridad: la key DEBE empezar con tenants/{tid}/..."""
    from uuid import uuid4
    from app.influencer.face_variations_router import _key_belongs_to_tenant
    tid = uuid4()
    assert _key_belongs_to_tenant(f'tenants/{tid}/influencer/x.png', tid) is True
    # Cross-tenant rechazado.
    other = uuid4()
    assert _key_belongs_to_tenant(f'tenants/{other}/influencer/x.png', tid) is False
    # Path absoluto rechazado.
    assert _key_belongs_to_tenant('/etc/passwd', tid) is False
    # Traversal rechazado por el prefijo (no empieza con `tenants/{tid}/`).
    assert _key_belongs_to_tenant('../../../etc/passwd', tid) is False


def test_serve_storage_asset_401_when_no_auth():
    """Sin actor_id en el request → 401 (auth required)."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import serve_storage_asset
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(actor_id=None))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    with _pytest.raises(HTTPException) as exc:
        asyncio.run(serve_storage_asset(
            object_key=f'tenants/{uuid4()}/influencer/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 401


def test_serve_storage_asset_400_when_invalid_key():
    """Path que no empieza con tenants/{uuid}/ → 400."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import serve_storage_asset
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(
        actor_id=uuid4(), support_mode=False,
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    with _pytest.raises(HTTPException) as exc:
        asyncio.run(serve_storage_asset(
            object_key='not-a-tenants-path/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 400


def test_serve_storage_asset_403_when_user_not_member():
    """User autenticado pero sin row en user_tenant_roles → 403."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import serve_storage_asset
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(
        actor_id=uuid4(), support_mode=False,
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)  # no membership
    with _pytest.raises(HTTPException) as exc:
        asyncio.run(serve_storage_asset(
            object_key=f'tenants/{uuid4()}/influencer/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 403


def test_extract_tenant_id_from_key():
    """Helper interno: extracción del tenant_id desde el path."""
    from uuid import uuid4
    from app.influencer.face_variations_router import _extract_tenant_id_from_key
    tid = uuid4()
    assert _extract_tenant_id_from_key(f'tenants/{tid}/influencer/x.png') == tid
    assert _extract_tenant_id_from_key('foo/bar/baz.png') is None
    assert _extract_tenant_id_from_key('tenants/not-a-uuid/x.png') is None
    assert _extract_tenant_id_from_key('') is None


def test_storage_key_to_url_passthrough_data_url():
    """UI-INFLU-014.7: data URLs (base64 inline) son auto-contenidas y
    el navegador las renderiza directo — no las prefijamos."""
    from app.influencer.face_variations_router import _storage_key_to_url
    data_url = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA=='
    assert _storage_key_to_url(data_url) == data_url
    # También funciona con image/jpeg, image/webp, etc.
    jpeg = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA'
    assert _storage_key_to_url(jpeg) == jpeg


def test_storage_key_to_url_wraps_opaque_key():
    """Keys opacas se prefijan con el proxy del admin para que el browser
    autenticado las pueda servir."""
    from app.influencer.face_variations_router import _storage_key_to_url
    url = _storage_key_to_url('tenants/abc/influencer/personas/xyz/face_variations/req-1/0')
    assert url.startswith('/admin/api/core/v1/influencer/storage/')
    assert 'tenants/abc' in url


def test_migration_adds_face_variation_request_id_to_assets():
    """La migración debe agregar la FK assets.face_variation_request_id."""
    assert 'add column if not exists face_variation_request_id' in SCHEMA_SRC
    assert (
        'references influencer.face_variation_requests(id)' in SCHEMA_SRC
        or 'references influencer.face_variation_requests (id)' in SCHEMA_SRC
    )
    assert 'ix_assets_face_variation_request' in SCHEMA_SRC


# ─── Dynamic: endpoint handlers (require_tenant_id + create + status) ──────


def test_require_tenant_id_raises_when_missing():
    """`_require_tenant_id` falla con 404 cuando no hay tenant en el request."""
    from fastapi import HTTPException
    from app.influencer.face_variations_router import _require_tenant_id
    from types import SimpleNamespace
    import pytest as _pytest
    fake_request = SimpleNamespace(state=SimpleNamespace())
    with _pytest.raises(HTTPException) as exc:
        _require_tenant_id(fake_request)
    assert exc.value.status_code == 404


def test_require_tenant_id_returns_uuid():
    """Devuelve el UUID tal cual cuando el state tiene un tenant válido."""
    from uuid import uuid4
    from app.influencer.face_variations_router import _require_tenant_id
    from types import SimpleNamespace
    tid = uuid4()
    fake_request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    assert _require_tenant_id(fake_request) == tid


def test_require_tenant_id_coerces_string_to_uuid():
    """Acepta string y lo convierte a UUID."""
    from uuid import uuid4
    from app.influencer.face_variations_router import _require_tenant_id
    from types import SimpleNamespace
    tid = uuid4()
    fake_request = SimpleNamespace(state=SimpleNamespace(tenant_id=str(tid)))
    assert _require_tenant_id(fake_request) == tid


def test_create_face_variations_handler_happy_path(monkeypatch):
    """Test directo del handler async — sin TestClient para velocidad.
    UI-INFLU-014.3 SÍNCRONO: el handler llama al provider, espera, y
    devuelve assets pobladas + status='completed'.
    UI-INFLU-014.7: storage real (mockeamos store_face_variation_asset).
    """
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace
    from app.influencer import face_variations_router as fvr
    from app.ai.providers.base import ImageResult
    from app.services.influencer_storage import StoredInfluencerAsset

    tenant_id = uuid4()
    persona_id = uuid4()
    req_id = uuid4()
    asset_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=uuid4(),
    ))

    # Mock del adapter: devuelve 1 ImageResult con bytes PNG.
    fake_adapter = MagicMock()
    fake_adapter._models = {}
    fake_adapter.generate_image = AsyncMock(return_value=[
        ImageResult(image_bytes=b'\x89PNG-test', mime='image/png',
                    width=1024, height=1024),
    ])
    monkeypatch.setattr(fvr, '_build_test_provider', lambda *a, **kw: fake_adapter)
    monkeypatch.setattr(fvr, '_decrypt_secret', lambda c: 'fake-key')
    # Mock storage para no escribir a disco real durante el test.
    fake_key = f'tenants/{tenant_id}/influencer/face-variations/{req_id}/0.png'
    monkeypatch.setattr(
        fvr, 'store_face_variation_asset',
        lambda **kw: StoredInfluencerAsset(
            storage_backend='local', bucket=None,
            object_key=fake_key,
            source_uri=f'file:///tmp/{fake_key}',
            size_bytes=len(kw['data']), mime='image/png',
        ),
    )
    # Mock storage config fetch: devuelve config local mínima.
    async def _fake_fetch_config(conn, tid):
        return {'backend': 'local', 'bucket': None, 'prefix': None}
    monkeypatch.setattr(
        fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch_config,
    )

    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona_row = {
        'id': persona_id,
        'face': {'ethnicity': 'latina', 'eye_color': 'brown'},
        'body': {'silhouette': 'athletic'},
        'identity': {},
        'voice': {},
        'status': 'draft',
    }
    created_row = {
        'id': req_id, 'persona_id': persona_id, 'requested_count': 1,
        'status': 'in_progress', 'prompt_used': 'whatever', 'error_message': None,
    }
    provider_row = {
        'provider': 'grok', 'model': 'grok-2-image',
        'hint': 'abcd', 'ciphertext': b'fake-cipher',
    }
    asset_row = {'id': asset_id, 'marked_canonical': False}
    conn.fetchrow = AsyncMock(side_effect=[
        persona_row, created_row, provider_row, asset_row,
    ])

    resp = asyncio.run(fvr.create_face_variations(
        persona_id=persona_id, request=request,
        body=fvr.VariationRequest(count=1), conn=conn,
    ))
    assert resp.id == req_id
    assert resp.status == 'completed'  # síncrono: ya completed
    assert len(resp.assets) == 1
    assert resp.assets[0].id == asset_id
    # UI-INFLU-014.7: la URL es ahora el endpoint del storage proxy
    # (no data: inline), porque store_face_variation_asset devolvió
    # una key opaca tipo `tenants/.../influencer/face-variations/...`.
    assert resp.assets[0].url.startswith('/admin/api/core/v1/influencer/storage/')
    assert 'tenants/' in resp.assets[0].url
    # El prompt debe incluir face+body.
    fake_adapter.generate_image.assert_awaited_once()
    prompt_arg = fake_adapter.generate_image.call_args.kwargs['prompt']
    assert 'latina' in prompt_arg
    assert 'athletic' in prompt_arg


def test_create_face_variations_persona_missing_404():
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import (
        create_face_variations,
        VariationRequest,
    )
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=uuid4(), user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)  # persona not found

    with _pytest.raises(HTTPException) as exc:
        asyncio.run(create_face_variations(
            persona_id=uuid4(), request=request,
            body=VariationRequest(), conn=conn,
        ))
    assert exc.value.status_code == 404


def test_create_face_variations_archived_persona_409():
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import (
        create_face_variations,
        VariationRequest,
    )
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=uuid4(), user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={
        'id': uuid4(), 'face': {}, 'body': {}, 'identity': {}, 'voice': {},
        'status': 'archived',
    })
    with _pytest.raises(HTTPException) as exc:
        asyncio.run(create_face_variations(
            persona_id=uuid4(), request=request,
            body=VariationRequest(), conn=conn,
        ))
    assert exc.value.status_code == 409


def test_get_face_variation_status_includes_assets():
    """El GET de status hace JOIN con assets y devuelve URLs."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from app.influencer.face_variations_router import get_face_variation_status

    tenant_id = uuid4()
    persona_id = uuid4()
    req_id = uuid4()
    asset_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # Primera fetchrow: el request. Segunda fetch: assets.
    conn.fetchrow = AsyncMock(return_value={
        'id': req_id, 'persona_id': persona_id, 'requested_count': 1,
        'status': 'completed', 'prompt_used': 'whatever',
        'error_message': None,
    })
    conn.fetch = AsyncMock(return_value=[
        {
            'id': asset_id,
            'storage_key': f'tenants/{tenant_id}/influencer/personas/{persona_id}/face_variations/{req_id}/0',
            'mime': 'image/png', 'width': 1024, 'height': 1024,
            'marked_canonical': False,
        },
    ])

    resp = asyncio.run(get_face_variation_status(
        persona_id=persona_id, variation_request_id=req_id,
        request=request, conn=conn,
    ))
    assert resp.status == 'completed'
    assert len(resp.assets) == 1
    assert resp.assets[0].id == asset_id
    assert resp.assets[0].url.startswith('/admin/api/core/v1/influencer/storage/')


def test_create_face_variations_unconfigured_provider_503(monkeypatch):
    """Si el provider no está configurado, el handler levanta 503."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer import face_variations_router as fvr
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=uuid4(), user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona_row = {
        'id': uuid4(), 'face': {}, 'body': {}, 'identity': {}, 'voice': {},
        'status': 'draft',
    }
    created_row = {
        'id': uuid4(), 'persona_id': uuid4(), 'requested_count': 1,
        'status': 'in_progress', 'prompt_used': '', 'error_message': None,
    }
    # provider_row: provider='unset' → falla con 503
    conn.fetchrow = AsyncMock(side_effect=[
        persona_row, created_row,
        {'provider': 'unset', 'model': None, 'hint': None, 'ciphertext': None},
    ])

    with _pytest.raises(HTTPException) as exc:
        asyncio.run(fvr.create_face_variations(
            persona_id=uuid4(), request=request,
            body=fvr.VariationRequest(), conn=conn,
        ))
    assert exc.value.status_code == 503


def test_create_face_variations_provider_content_rejected_422(monkeypatch):
    """ProviderContentRejected → 422 + marca request failed."""
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer import face_variations_router as fvr
    from app.ai.providers.base import ProviderContentRejected
    import pytest as _pytest

    adapter = MagicMock()
    adapter._models = {}
    adapter.generate_image = AsyncMock(side_effect=ProviderContentRejected('nsfw'))
    monkeypatch.setattr(fvr, '_build_test_provider', lambda *a, **kw: adapter)
    monkeypatch.setattr(fvr, '_decrypt_secret', lambda c: 'fake-key')

    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=uuid4(), user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(side_effect=[
        {'id': uuid4(), 'face': {}, 'body': {}, 'identity': {}, 'voice': {},
         'status': 'draft'},
        {'id': uuid4(), 'persona_id': uuid4(), 'requested_count': 1,
         'status': 'in_progress', 'prompt_used': '', 'error_message': None},
        {'provider': 'grok', 'model': 'grok-2-image',
         'hint': 'abcd', 'ciphertext': b'fake-cipher'},
    ])

    with _pytest.raises(HTTPException) as exc:
        asyncio.run(fvr.create_face_variations(
            persona_id=uuid4(), request=request,
            body=fvr.VariationRequest(), conn=conn,
        ))
    assert exc.value.status_code == 422
    assert 'content rejected' in str(exc.value.detail).lower()


def test_get_face_variation_status_404_when_request_missing():
    import asyncio
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.influencer.face_variations_router import get_face_variation_status
    import pytest as _pytest

    request = SimpleNamespace(state=SimpleNamespace(tenant_id=uuid4()))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    with _pytest.raises(HTTPException) as exc:
        asyncio.run(get_face_variation_status(
            persona_id=uuid4(), variation_request_id=uuid4(),
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 404


def test_migration_creates_face_variation_requests():
    assert 'create table if not exists influencer.face_variation_requests' in SCHEMA_SRC
    assert "status in ('queued', 'in_progress', 'completed', 'failed')" in SCHEMA_SRC


def test_migration_count_range_check():
    assert 'requested_count between 1 and 10' in SCHEMA_SRC


def test_migration_index_for_worker_queue():
    """Index sobre status='queued' o 'in_progress' para que el worker
    picke jobs rápido."""
    assert 'ix_face_variation_requests_queued' in SCHEMA_SRC
    assert "status in ('queued', 'in_progress')" in SCHEMA_SRC


def test_migration_rls_enabled():
    # Buscar la sección específica de face_variation_requests
    fvr_idx = SCHEMA_SRC.find('influencer.face_variation_requests')
    assert fvr_idx > 0
    section = SCHEMA_SRC[fvr_idx:fvr_idx + 2000]
    assert 'enable row level security' in section
    assert 'fvr_tenant_isolation' in section


def test_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'face_variations_router' in main_src
    assert 'include_router(influencer_face_variations_router)' in main_src
