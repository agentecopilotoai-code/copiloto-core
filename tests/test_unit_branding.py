"""Tests para `copiloto_core.branding.BrandingConfig` + endpoint
GET /v1/branding (Fase 8).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from copiloto_core import BrandingConfig, create_app


# ─── BrandingConfig validation ───────────────────────────────────────────


def test_default_branding_is_copilotoia():
    b = BrandingConfig()
    assert b.product_name == 'CopilotoIA'
    assert b.copyright_holder == 'CopilotoIA'
    assert b.primary_color.startswith('#')
    assert b.accent_color.startswith('#')


def test_custom_branding():
    b = BrandingConfig(
        product_name='SAT Monitoreo',
        logo_url='/static/logo.svg',
        primary_color='#0F1E33',
        support_email='soporte@sat.com',
    )
    assert b.product_name == 'SAT Monitoreo'
    assert b.logo_url == '/static/logo.svg'
    assert b.support_email == 'soporte@sat.com'


def test_color_without_hash_normalized():
    """Auto-añade `#` si falta."""
    b = BrandingConfig(primary_color='abc123', accent_color='def456')
    assert b.primary_color == '#abc123'
    assert b.accent_color == '#def456'


def test_color_uppercase_normalized_to_lowercase():
    b = BrandingConfig(primary_color='#ABCDEF')
    assert b.primary_color == '#abcdef'


def test_color_3_chars_accepted():
    b = BrandingConfig(primary_color='#abc')
    assert b.primary_color == '#abc'


def test_empty_product_name_rejected():
    with pytest.raises(ValueError, match='product_name'):
        BrandingConfig(product_name='')


def test_invalid_color_rejected():
    with pytest.raises(ValueError, match='hex color'):
        BrandingConfig(primary_color='not-a-color')


def test_non_str_product_name_rejected():
    with pytest.raises(ValueError):
        BrandingConfig(product_name=42)  # type: ignore[arg-type]


def test_to_public_dict_includes_all_fields():
    b = BrandingConfig(
        product_name='X', logo_url='/l.svg',
        support_email='s@x.com', privacy_url='/privacy',
    )
    d = b.to_public_dict()
    # Shape consistente — todos los campos presentes (incluso None)
    expected_keys = {
        'product_name', 'logo_url', 'primary_color', 'accent_color',
        'support_email', 'copyright_holder', 'privacy_url', 'terms_url',
    }
    assert set(d.keys()) == expected_keys
    assert d['product_name'] == 'X'
    assert d['terms_url'] is None
    assert d['privacy_url'] == '/privacy'


# ─── /v1/branding endpoint ───────────────────────────────────────────────


def test_branding_endpoint_default():
    app = create_app()
    client = TestClient(app)
    resp = client.get('/v1/branding')
    assert resp.status_code == 200
    data = resp.json()
    assert data['product_name'] == 'CopilotoIA'
    assert data['primary_color'].startswith('#')


def test_branding_endpoint_custom():
    app = create_app(
        branding=BrandingConfig(
            product_name='SAT Monitoreo',
            primary_color='#123456',
            support_email='ayuda@sat.com',
        ),
    )
    client = TestClient(app)
    resp = client.get('/v1/branding')
    assert resp.status_code == 200
    data = resp.json()
    assert data['product_name'] == 'SAT Monitoreo'
    assert data['primary_color'] == '#123456'
    assert data['support_email'] == 'ayuda@sat.com'


def test_branding_endpoint_is_public_no_auth():
    """No requiere Authorization header — el SPA lo carga antes del login."""
    app = create_app(branding=BrandingConfig(product_name='X'))
    client = TestClient(app)
    resp = client.get('/v1/branding')  # sin Authorization
    assert resp.status_code == 200


def test_branding_stored_in_app_state():
    """Útil para módulos que quieren leer la marca del deployment
    para sus emails / templates."""
    app = create_app(
        branding=BrandingConfig(product_name='Acme Inc', primary_color='#abc'),
    )
    assert app.state.branding.product_name == 'Acme Inc'
    assert app.state.branding.primary_color == '#abc'
