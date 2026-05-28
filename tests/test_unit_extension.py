"""Tests para `copiloto_core.extension.CoreModule` (Fase 3 — modelo
extension del core).

Cubre las validaciones del dataclass + property `url_prefix`. El uso
real (montar el router, seedear capabilities, correr migrations) se
valida en Fase 11 con un E2E.
"""
from __future__ import annotations

import pytest
from fastapi import APIRouter

from copiloto_core.extension import CoreModule


# ─── code validation ─────────────────────────────────────────────────────


def test_valid_code_accepted():
    m = CoreModule(code='mi_modulo', router=APIRouter())
    assert m.code == 'mi_modulo'


def test_code_with_digits_accepted():
    m = CoreModule(code='m2m_proxy', router=APIRouter())
    assert m.code == 'm2m_proxy'


def test_code_starting_with_digit_rejected():
    with pytest.raises(ValueError, match='snake_case'):
        CoreModule(code='2nd_module', router=APIRouter())


def test_code_uppercase_rejected():
    with pytest.raises(ValueError, match='snake_case'):
        CoreModule(code='MiModulo', router=APIRouter())


def test_code_with_dash_rejected():
    """Dashes son para URL, no para code."""
    with pytest.raises(ValueError, match='snake_case'):
        CoreModule(code='mi-modulo', router=APIRouter())


def test_code_too_short_rejected():
    with pytest.raises(ValueError):
        CoreModule(code='m', router=APIRouter())


def test_code_too_long_rejected():
    with pytest.raises(ValueError):
        CoreModule(code='a' * 33, router=APIRouter())


def test_code_non_str_rejected():
    with pytest.raises(ValueError):
        CoreModule(code=42, router=APIRouter())  # type: ignore[arg-type]


# ─── router validation ───────────────────────────────────────────────────


def test_router_must_be_apirouter():
    with pytest.raises(ValueError, match='APIRouter'):
        CoreModule(code='ok', router='no soy un router')  # type: ignore[arg-type]


# ─── capabilities validation ─────────────────────────────────────────────


def test_capabilities_with_correct_namespace():
    m = CoreModule(
        code='crm',
        router=APIRouter(),
        capabilities=('crm:contacts:read', 'crm:contacts:write'),
    )
    assert len(m.capabilities) == 2


def test_capabilities_without_colon_rejected():
    with pytest.raises(ValueError, match='<code>:<accion>'):
        CoreModule(
            code='crm', router=APIRouter(),
            capabilities=('contacts_read',),
        )


def test_capabilities_wrong_namespace_rejected():
    """Cada cap debe arrancar con el code del módulo (anti-colisión)."""
    with pytest.raises(ValueError, match='namespace'):
        CoreModule(
            code='crm', router=APIRouter(),
            capabilities=('helpdesk:tickets:read',),
        )


# ─── static_mounts validation ────────────────────────────────────────────


def test_static_mounts_valid():
    m = CoreModule(
        code='ok',
        router=APIRouter(),
        static_mounts={'/admin': 'ok/spa/dist', '/landing': 'ok/landing/dist'},
    )
    assert len(m.static_mounts) == 2


def test_static_mount_without_leading_slash_rejected():
    with pytest.raises(ValueError, match='/'):
        CoreModule(
            code='ok', router=APIRouter(),
            static_mounts={'admin': 'spa/dist'},
        )


# ─── url_prefix property ─────────────────────────────────────────────────


def test_url_prefix_kebab_case_from_snake():
    m = CoreModule(code='mi_modulo_largo', router=APIRouter())
    assert m.url_prefix == '/v1/mi-modulo-largo'


def test_url_prefix_no_underscore_passthrough():
    m = CoreModule(code='crm', router=APIRouter())
    assert m.url_prefix == '/v1/crm'


# ─── frozen ──────────────────────────────────────────────────────────────


def test_module_is_frozen():
    m = CoreModule(code='ok', router=APIRouter())
    with pytest.raises(AttributeError):
        m.code = 'mutated'  # type: ignore[misc]
