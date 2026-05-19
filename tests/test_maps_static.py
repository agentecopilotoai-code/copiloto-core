"""Static tests for TASK-0058 — Auto-generación del link de Google Maps.

Coverage:
- ``build_maps_url`` prefers coordinates over address.
- Falls back to the URL-encoded address when only address is given.
- Returns ``None`` if neither input is usable.
- Validates coordinate ranges (rejects out-of-range lat/lng).
- Encodes special characters in addresses correctly.
- ``create_branch`` and ``update_branch`` wire the helper into the route.
- Admin Panel exposes the "Generar desde la dirección" button + preview.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from app.api.v1 import routes as routes_module
from app.services.maps import MAPS_BASE_URL, build_maps_url
from tests._routes_aggregator import routes_aggregated_source

# UI-007.7: the branches module was redesigned into a feature directory.
BRANCHES_FEATURE = Path('admin-panel/src/features/owner-admin/branches')


def _branches_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(BRANCHES_FEATURE.rglob('*.js*'))
    )


# ───── Builder ─────────────────────────────────────────────────────────────


def test_build_maps_url_prefers_coordinates_over_address():
    url = build_maps_url(4.65, -74.05, 'Cra 7 #45-20, Bogotá')
    assert url is not None
    assert url.startswith(MAPS_BASE_URL)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs['query'] == ['4.65,-74.05']
    assert qs['api'] == ['1']


def test_build_maps_url_falls_back_to_address_when_no_coords():
    url = build_maps_url(None, None, 'Cra 7 #45-20, Bogotá')
    assert url is not None
    # The full address (incl. accents and "#") must be URL-encoded.
    assert 'Cra%207%20%2345-20%2C%20Bogot%C3%A1' in url


def test_build_maps_url_returns_none_without_inputs():
    assert build_maps_url() is None
    assert build_maps_url(None, None, None) is None
    assert build_maps_url(None, None, '   ') is None


def test_build_maps_url_rejects_out_of_range_coords_and_uses_address():
    # Out-of-range lat → falls through to address branch instead of emitting a bad pin.
    url = build_maps_url(120.0, -74.0, 'Calle Falsa 123')
    assert url is not None
    assert 'Calle%20Falsa%20123' in url
    # Out-of-range lng → same fallback.
    url = build_maps_url(4.65, 999.0, 'Calle Falsa 123')
    assert 'Calle%20Falsa%20123' in url
    # No valid fallback either → None.
    assert build_maps_url(120.0, 999.0, None) is None


def test_build_maps_url_handles_string_numeric_inputs():
    # asyncpg may surface ``numeric`` columns as ``Decimal`` / ``str`` — the
    # helper must coerce them before formatting.
    url = build_maps_url('4.65', '-74.05', None)
    assert url is not None
    assert '4.65,-74.05' in url
    # Garbage strings fall through gracefully.
    assert build_maps_url('not-a-number', 'nope', None) is None


def test_build_maps_url_encodes_special_characters_in_address():
    url = build_maps_url(None, None, 'Av. Las Américas & Cl. 80, México')
    assert url is not None
    # ``&`` must not leak as a query separator — it has to be encoded.
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs['query'] == ['Av. Las Américas & Cl. 80, México']


# ───── Wiring into the routes ──────────────────────────────────────────────


def test_routes_imports_build_maps_url():
    source = routes_aggregated_source()
    assert 'from app.services.maps import build_maps_url' in source


def test_create_branch_auto_generates_maps_url_when_blank():
    source = inspect.getsource(routes_module.create_branch)
    assert 'maps_url_value' in source
    assert 'build_maps_url(payload.lat, payload.lng, payload.address)' in source
    assert 'if not maps_url_value' in source


def test_update_branch_regenerates_maps_url_when_cleared():
    source = inspect.getsource(routes_module.update_branch)
    assert "'maps_url' in update_data" in source
    assert 'build_maps_url(final_lat, final_lng, final_address)' in source
    # Falls back to existing row values when the admin did not touch coords/address.
    assert "'lat' in update_data" in source
    assert "'address' in update_data" in source


# ───── Admin Panel UI ──────────────────────────────────────────────────────


def test_branches_module_exposes_generate_button_and_preview():
    source = _branches_feature_source()
    assert 'buildMapsUrlFromInputs' in source
    assert 'Generar desde la dirección' in source
    assert 'data-testid="branches-maps-generate"' in source
    assert 'branches-maps-preview' in source
    # Mirror of the backend canonical URL format.
    assert "'https://www.google.com/maps/search/?api=1&query='" in source
