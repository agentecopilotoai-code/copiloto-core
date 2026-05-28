"""Tests del BFF admin — específicamente la lógica de inyección de
X-Tenant-Id desde la cookie de support_mode, y la distinción
platform-scoped vs tenant-scoped.

Regresión crítica: si el BFF inyectara X-Tenant-Id en TODAS las requests,
endpoints como `/v1/tenants` (platform-scoped, requiere token UNSCOPED)
fallarían con 403 "Platform administration requires an unscoped token"
para cualquier platform_owner que tenga una cookie de support_mode
activa para un tenant específico. Caso bloqueante.
"""
from __future__ import annotations

import pytest

from copiloto_core.admin.routes import _is_platform_scoped_path


class TestIsPlatformScopedPath:
    """Identifica paths que requieren un token UNSCOPED upstream."""

    @pytest.mark.parametrize(
        'path',
        [
            'v1/tenants',
            '/v1/tenants',
            'v1/tenants?limit=100',
            'v1/tenants?limit=100&offset=0',
            'v1/tenants/abc-123-uuid',
            'v1/tenants/abc-123-uuid/members',
            'v1/tenants/abc/modules',
        ],
    )
    def test_tenants_paths_son_platform_scoped(self, path: str) -> None:
        assert _is_platform_scoped_path(path) is True

    @pytest.mark.parametrize(
        'path',
        [
            'v1/platform/incidents',
            'v1/platform/ai-providers',
            'v1/platform/tenant-modules',
            'v1/platform/runbooks',
            'v1/platform/feature-flags',
            '/v1/platform/anything',
        ],
    )
    def test_platform_admin_paths_son_platform_scoped(self, path: str) -> None:
        assert _is_platform_scoped_path(path) is True

    @pytest.mark.parametrize(
        'path',
        [
            'v1/me',
            'v1/me/tenants',
            'v1/me/support-mode/some-uuid',
            '/v1/me/preferences',
        ],
    )
    def test_me_paths_son_platform_scoped(self, path: str) -> None:
        # `/v1/me/*` son user-scoped, NO tenant-scoped — no requieren
        # X-Tenant-Id. El BFF no debe inyectarlo desde la cookie.
        assert _is_platform_scoped_path(path) is True

    @pytest.mark.parametrize(
        'path',
        [
            'v1/core/auditoria',
            'v1/health',
            'v1/anything-not-platform',
        ],
    )
    def test_module_paths_son_tenant_scoped(self, path: str) -> None:
        # Endpoints scoped al tenant — necesitan X-Tenant-Id. El BFF SÍ
        # debe inyectarlo desde la cookie cuando el browser no lo manda
        # explícito. (En el core puro no hay paths así; cada módulo opt-in
        # registra sus propios paths bajo su prefix.)
        assert _is_platform_scoped_path(path) is False

    def test_path_vacio_no_es_platform_scoped(self) -> None:
        # Defensa contra string vacío — no debe explotar, devuelve False
        # (no es platform-scoped, así que el BFF intenta inyectar el header
        # de cookie si está; backend rechaza con 404 igual).
        assert _is_platform_scoped_path('') is False
