"""Tests estáticos para `app.gd.handlers.me_handlers` (GD-API-0002).

Cubre:
- Heurística de `_split_display_name` (parsing nombres/apellidos).
- Estructura del schema `GdMeResponse` (campos requeridos, tipos).
- Router se importa sin errores y declara la ruta /me.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from app.gd.handlers.me_handlers import _split_display_name, router
from app.gd.schemas.identidad import (
    GdMeCargo,
    GdMeDependencia,
    GdMePerfilSection,
    GdMeResponse,
    GdMeRolVigente,
)


class TestSplitDisplayName:
    """Heurística para separar nombres/apellidos del display_name."""

    @pytest.mark.parametrize(
        ('display_name', 'nombres', 'apellidos'),
        [
            # Dos nombres + dos apellidos (caso típico CO)
            ('Juan Carlos Pérez García', 'Juan Carlos', 'Pérez García'),
            # Un nombre + un apellido
            ('Juan Pérez', 'Juan', 'Pérez'),
            # Un nombre + dos apellidos
            ('Juan Pérez García', 'Juan Pérez', 'García'),
            # Tres nombres + dos apellidos
            ('María del Carmen Pérez García', 'María del Carmen', 'Pérez García'),
            # Solo nombre (edge case)
            ('Madonna', 'Madonna', ''),
            # Vacío
            ('', '', ''),
            ('   ', '', ''),
        ],
    )
    def test_split(self, display_name: str, nombres: str, apellidos: str) -> None:
        assert _split_display_name(display_name) == (nombres, apellidos)


class TestGdMeResponseSchema:
    """El response /me debe poder construirse y serializarse correctamente."""

    def test_response_minimo_solo_campos_requeridos(self) -> None:
        # Permite ver qué campos son realmente requeridos.
        response = GdMeResponse(
            user_id=uuid4(),
            email='test@example.com',
            nombres='Test',
            apellidos='User',
            perfil_gd=GdMePerfilSection(
                tipo_vinculacion='planta',
                estado_gd='activo',
            ),
        )
        # roles, permisos y modulos default a [].
        assert response.roles_gd_vigentes == []
        assert response.permisos_efectivos == []
        assert response.modulos_activos_organizacion == []
        assert response.dependencia_actual is None
        assert response.cargo_actual is None

    def test_response_completo_serializable(self) -> None:
        user_id = uuid4()
        tenant_dep_id = uuid4()
        cargo_id = uuid4()
        asignacion_id = uuid4()
        response = GdMeResponse(
            user_id=user_id,
            email='juan@entidad.gov.co',
            nombres='Juan Carlos',
            apellidos='Pérez García',
            perfil_gd=GdMePerfilSection(
                tipo_vinculacion='planta',
                estado_gd='activo',
                fecha_inicio_vinculacion=date(2025, 1, 15),
                fecha_fin_vinculacion=None,
                ultimo_acceso=datetime(2026, 5, 23, 8, 11, 0),
            ),
            dependencia_actual=GdMeDependencia(id=tenant_dep_id, codigo='JUR-001', nombre='Oficina Jurídica'),
            cargo_actual=GdMeCargo(id=cargo_id, nombre='Profesional Especializado'),
            roles_gd_vigentes=[
                GdMeRolVigente(
                    asignacion_alcance_id=asignacion_id,
                    rol_codigo='gd.profesional',
                    rol_nombre='Profesional Responsable',
                    dependencia_id=tenant_dep_id,
                    dependencia_nombre='Oficina Jurídica',
                    alcance='dependencia',
                    fecha_inicio=date(2025, 1, 15),
                    fecha_fin=None,
                )
            ],
            permisos_efectivos=['PERM-PQRSD-009', 'PERM-DOC-005'],
            modulos_activos_organizacion=['pqrsd_legal'],
        )
        # Pydantic v2: usar model_dump_json para verificar serialización.
        json_str = response.model_dump_json()
        assert 'gd.profesional' in json_str
        assert 'PERM-PQRSD-009' in json_str

    def test_alcance_solo_acepta_literales_definidos(self) -> None:
        # Literal['propio', 'dependencia', ...] — Pydantic rechaza otros.
        with pytest.raises(Exception):  # ValidationError es subclase
            GdMeRolVigente(
                asignacion_alcance_id=uuid4(),
                rol_codigo='gd.profesional',
                rol_nombre='X',
                alcance='inexistente',  # type: ignore[arg-type]
                fecha_inicio=date(2025, 1, 1),
            )


class TestRouterRegistra():
    """El router debe exponer /me con verbo GET."""

    def test_router_tiene_get_me(self) -> None:
        paths_methods = {
            (route.path, tuple(sorted(route.methods)))
            for route in router.routes
            if isinstance(route, APIRoute)
        }
        assert ('/me', ('GET',)) in paths_methods, (
            f'Esperaba GET /me en router.routes, encontré: {paths_methods}'
        )
