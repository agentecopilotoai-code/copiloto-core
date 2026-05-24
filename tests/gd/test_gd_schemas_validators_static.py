"""Tests para los validators custom de los schemas Pydantic del bloque 2."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.gd.handlers.perfil_usuario_handlers import _split_display_name
from app.gd.schemas.asignaciones import AsignacionRolCreate
from app.gd.schemas.perfil_usuario import PerfilUsuarioCreate
from app.gd.schemas.politica_contrasena import PoliticaContrasenaPatch
from app.gd.schemas.roles import RolCreate


class TestPerfilUsuarioValidators:
    def test_fecha_fin_anterior_falla(self) -> None:
        with pytest.raises(ValidationError):
            PerfilUsuarioCreate(
                user_id=uuid4(),
                tipo_vinculacion='planta',
                fecha_inicio_vinculacion=date(2026, 6, 1),
                fecha_fin_vinculacion=date(2026, 5, 1),  # anterior
                dependencia_actual_id=uuid4(),
            )

    def test_fecha_fin_posterior_ok(self) -> None:
        p = PerfilUsuarioCreate(
            user_id=uuid4(),
            tipo_vinculacion='planta',
            fecha_inicio_vinculacion=date(2026, 1, 1),
            fecha_fin_vinculacion=date(2026, 12, 31),
            dependencia_actual_id=uuid4(),
        )
        assert p.fecha_fin_vinculacion == date(2026, 12, 31)

    def test_fecha_fin_none_ok(self) -> None:
        p = PerfilUsuarioCreate(
            user_id=uuid4(),
            tipo_vinculacion='planta',
            fecha_inicio_vinculacion=date(2026, 1, 1),
            dependencia_actual_id=uuid4(),
        )
        assert p.fecha_fin_vinculacion is None


class TestRolCreateValidators:
    def test_codigo_sin_prefijo_gd_falla(self) -> None:
        with pytest.raises(ValidationError, match="gd\\."):
            RolCreate(codigo='custom_rol', nombre='Custom')

    def test_codigo_con_prefijo_gd_ok(self) -> None:
        r = RolCreate(codigo='gd.custom_rol', nombre='Custom Rol')
        assert r.codigo == 'gd.custom_rol'


class TestAsignacionRolCreateValidators:
    def test_dependencia_requerida_para_alcance_dependencia(self) -> None:
        with pytest.raises(ValidationError, match='dependencia_id es requerida'):
            AsignacionRolCreate(
                rol_codigo='gd.x',
                alcance='dependencia',
                fecha_inicio=date(2026, 1, 1),
                motivo='Motivo válido suficientemente largo',
            )

    def test_dependencia_requerida_para_dependencias_autorizadas(self) -> None:
        with pytest.raises(ValidationError, match='dependencia_id es requerida'):
            AsignacionRolCreate(
                rol_codigo='gd.x',
                alcance='dependencias_autorizadas',
                fecha_inicio=date(2026, 1, 1),
                motivo='Motivo válido suficientemente largo',
            )

    def test_dependencia_opcional_para_alcance_propio(self) -> None:
        a = AsignacionRolCreate(
            rol_codigo='gd.x',
            alcance='propio',
            fecha_inicio=date(2026, 1, 1),
            motivo='Motivo válido suficientemente largo',
        )
        assert a.dependencia_id is None

    def test_dependencia_opcional_para_institucional(self) -> None:
        a = AsignacionRolCreate(
            rol_codigo='gd.x',
            alcance='institucional',
            fecha_inicio=date(2026, 1, 1),
            motivo='Motivo válido suficientemente largo',
        )
        assert a.alcance == 'institucional'

    def test_dependencia_opcional_para_global(self) -> None:
        a = AsignacionRolCreate(
            rol_codigo='gd.x',
            alcance='global',
            fecha_inicio=date(2026, 1, 1),
            motivo='Motivo válido suficientemente largo',
        )
        assert a.alcance == 'global'

    def test_fecha_fin_anterior_falla(self) -> None:
        with pytest.raises(ValidationError):
            AsignacionRolCreate(
                rol_codigo='gd.x',
                alcance='propio',
                fecha_inicio=date(2026, 6, 1),
                fecha_fin=date(2026, 5, 1),
                motivo='Motivo válido suficientemente largo',
            )


class TestPoliticaContrasenaPatch:
    def test_regex_invalida_falla(self) -> None:
        with pytest.raises(ValidationError, match='regex'):
            PoliticaContrasenaPatch(complejidad_regex='[invalid')

    def test_regex_valida_ok(self) -> None:
        p = PoliticaContrasenaPatch(complejidad_regex=r'.+')
        assert p.complejidad_regex == r'.+'

    def test_longitud_fuera_de_rango(self) -> None:
        with pytest.raises(ValidationError):
            PoliticaContrasenaPatch(longitud_minima=5)  # < 6
        with pytest.raises(ValidationError):
            PoliticaContrasenaPatch(longitud_minima=300)  # > 256

    def test_extra_field_rechazado(self) -> None:
        # ConfigDict(extra='forbid')
        with pytest.raises(ValidationError):
            PoliticaContrasenaPatch(campo_inexistente='x')  # type: ignore[call-arg]


class TestSplitDisplayNameLocal:
    """Cubre la copia local de _split_display_name en perfil_usuario_handlers."""

    def test_vacio(self) -> None:
        assert _split_display_name('') == ('', '')

    def test_solo_espacios(self) -> None:
        assert _split_display_name('   ') == ('', '')

    def test_none(self) -> None:
        assert _split_display_name(None) == ('', '')

    def test_un_nombre(self) -> None:
        assert _split_display_name('Madonna') == ('Madonna', '')

    def test_dos_partes(self) -> None:
        assert _split_display_name('Juan Pérez') == ('Juan', 'Pérez')

    def test_tres_partes(self) -> None:
        assert _split_display_name('Juan Carlos Pérez') == ('Juan Carlos', 'Pérez')

    def test_cuatro_partes(self) -> None:
        assert _split_display_name('Juan Carlos Pérez García') == ('Juan Carlos', 'Pérez García')


class TestAsignacionFechaFinValidator:
    """Cubre el field_validator de fecha_fin en AsignacionRolCreate."""

    def test_fecha_fin_anterior_a_inicio_falla(self) -> None:
        with pytest.raises(ValidationError):
            AsignacionRolCreate(
                rol_codigo='gd.x',
                alcance='propio',
                fecha_inicio=date(2026, 6, 1),
                fecha_fin=date(2026, 1, 1),
                motivo='Motivo válido con suficientes caracteres',
            )

    def test_fecha_fin_none_es_valida(self) -> None:
        a = AsignacionRolCreate(
            rol_codigo='gd.x',
            alcance='propio',
            fecha_inicio=date(2026, 6, 1),
            fecha_fin=None,
            motivo='Motivo válido con suficientes caracteres',
        )
        assert a.fecha_fin is None
