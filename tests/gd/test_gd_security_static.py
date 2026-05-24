"""Tests estáticos para `app.gd.security` (GD-API-0002).

Cubre lógica pura sin tocar DB:
- Ranking de alcances (`_ALCANCE_RANK`).
- Función `_alcance_es_suficiente` (heurística de cobertura).
- Estructura de `GdPerfilContext` (inmutabilidad).

Tests con DB (require_gd_perfil, get_permisos_efectivos contra Postgres real)
van en test_gd_security_integration.py.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.gd.security import (
    GdPerfilContext,
    _ALCANCE_RANK,
    _alcance_es_suficiente,
)


class TestAlcanceRanking:
    """El orden de alcances es crítico para validación de permisos."""

    def test_alcances_estan_en_orden_creciente(self) -> None:
        """propio < dependencia < dependencias_autorizadas < institucional < global."""
        orden_esperado = [
            'propio',
            'dependencia',
            'dependencias_autorizadas',
            'institucional',
            'global',
        ]
        ranks = [_ALCANCE_RANK[a] for a in orden_esperado]
        assert ranks == sorted(ranks), (
            f'_ALCANCE_RANK debe estar en orden creciente. Orden actual: '
            f'{[(a, _ALCANCE_RANK[a]) for a in orden_esperado]}'
        )

    def test_todos_los_alcances_del_check_sql_estan_mapeados(self) -> None:
        """SQL define check (alcance in ('propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global'))."""
        esperados = {
            'propio',
            'dependencia',
            'dependencias_autorizadas',
            'institucional',
            'global',
        }
        assert set(_ALCANCE_RANK.keys()) == esperados, (
            'Mapping de alcances desfasado de SQL — actualizar uno o ambos lados.'
        )


class TestAlcanceEsSuficiente:
    """Validación de cobertura de alcance del usuario sobre el requerido."""

    @pytest.mark.parametrize(
        ('usuario', 'requerido', 'esperado'),
        [
            ('global', 'propio', True),
            ('global', 'global', True),
            ('institucional', 'dependencia', True),
            ('dependencia', 'propio', True),
            ('propio', 'propio', True),
            # Insuficiente
            ('propio', 'dependencia', False),
            ('dependencia', 'institucional', False),
            ('institucional', 'global', False),
            # None (usuario sin permiso)
            (None, 'propio', False),
            (None, 'global', False),
        ],
    )
    def test_combinatorias(
        self, usuario: str | None, requerido: str, esperado: bool
    ) -> None:
        assert _alcance_es_suficiente(usuario, requerido) is esperado


class TestGdPerfilContextInmutable:
    """`GdPerfilContext` debe ser frozen para no permitir mutación en request.state."""

    def test_es_frozen(self) -> None:
        ctx = GdPerfilContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            perfil_id=uuid4(),
            tipo_vinculacion='planta',
            estado_gd='activo',
            dependencia_actual_id=None,
            cargo_actual_id=None,
        )
        with pytest.raises(Exception):  # FrozenInstanceError es subclase de Exception
            ctx.estado_gd = 'inactivo'  # type: ignore[misc]
