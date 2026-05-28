"""Tests para `copiloto_core.scaffolding` (v1.1.0 — comando new-project).

Cubre:
  - Validación de slug del proyecto y módulo (regex, longitud).
  - Conversión kebab → snake.
  - Default del module_name (`<project_package>_modulo`).
  - Default del core_version (= __version__).
  - Override de --module-name + --target-dir.
  - Detección de colisión (module_name == project_package).
  - Idempotencia destructiva: si target_dir tiene contenido, raise.
  - Estructura completa de archivos generados.
  - pyproject.toml + .env.example + main.py renderizan placeholders.
  - main.py importa el módulo demo correctamente.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from copiloto_core import __version__ as CORE_VERSION
from copiloto_core.scaffolding import (
    GenerationResult,
    InvalidGitProtocolError,
    InvalidModuleNameError,
    InvalidProjectNameError,
    ProjectExistsError,
    generate_project,
)


# ─── Validación de slugs ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    'bad_name',
    [
        '',
        'A',                  # no minúscula
        'Mi-Saas',            # mayúscula
        '1mi-saas',           # empieza con dígito
        'mi_saas',            # underscore (esto es para `--module-name`)
        'mi saas',            # space
        'mi-saas!',           # char no permitido
        'a',                  # < 2 chars
        'x' * 49,             # > 48 chars
    ],
)
def test_invalid_project_name_raises(tmp_path: Path, bad_name: str) -> None:
    with pytest.raises(InvalidProjectNameError):
        generate_project(project_name=bad_name, target_dir=tmp_path / 'p')


@pytest.mark.parametrize(
    'bad_module',
    [
        '',
        'Mi-Modulo',
        '1modulo',
        'mi-modulo',          # kebab no permitido en module
        'a',
        'x' * 33,
    ],
)
def test_invalid_module_name_raises(tmp_path: Path, bad_module: str) -> None:
    with pytest.raises(InvalidModuleNameError):
        generate_project(
            project_name='mi-saas',
            target_dir=tmp_path / 'p',
            module_name=bad_module,
        )


def test_module_name_cannot_equal_project_package(tmp_path: Path) -> None:
    with pytest.raises(InvalidModuleNameError, match='no puede ser igual'):
        generate_project(
            project_name='mi-saas',
            target_dir=tmp_path / 'p',
            module_name='mi_saas',  # = project_package, prohibido
        )


# ─── Defaults + naming ──────────────────────────────────────────────────


def test_default_module_name_derived_from_project(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'mi-saas',
    )
    assert result.project_name == 'mi-saas'
    assert result.project_package == 'mi_saas'
    assert result.module_package == 'mi_saas_modulo'


def test_module_name_override_respected(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'mi-saas',
        module_name='alertas',
    )
    assert result.module_package == 'alertas'


def test_default_core_version_matches_package(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    assert result.core_version == CORE_VERSION


def test_core_version_override(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        core_version='1.1.0-rc1',
    )
    assert result.core_version == '1.1.0-rc1'


# ─── Idempotencia destructiva ────────────────────────────────────────────


def test_target_dir_with_content_raises(tmp_path: Path) -> None:
    target = tmp_path / 'mi-saas'
    target.mkdir()
    (target / 'pre-existing.txt').write_text('hola')
    with pytest.raises(ProjectExistsError):
        generate_project(project_name='mi-saas', target_dir=target)


def test_target_dir_empty_is_reused(tmp_path: Path) -> None:
    """Un directorio vacío ya creado por el user (ej. `mkdir mi-saas && cd …`)
    es válido — no forzamos a borrarlo."""
    target = tmp_path / 'mi-saas'
    target.mkdir()
    result = generate_project(project_name='mi-saas', target_dir=target)
    assert result.target_dir == target.resolve()


def test_target_dir_default_to_cwd_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = generate_project(project_name='mi-saas')
    assert result.target_dir == (tmp_path / 'mi-saas').resolve()


# ─── Estructura completa de archivos ─────────────────────────────────────


def test_generates_expected_file_tree(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'mi-saas',
    )
    expected = {
        '.env.example',
        '.gitignore',
        'README.md',
        'pyproject.toml',
        'mi_saas/__init__.py',
        'mi_saas/main.py',
        'mi_saas_modulo/__init__.py',
        'mi_saas_modulo/routers.py',
        'mi_saas_modulo/migrations/001_init.sql',
    }
    assert set(result.files_written) == expected
    for rel in expected:
        assert (result.target_dir / rel).is_file(), f'missing: {rel}'


# ─── Templates renderizan correctamente ──────────────────────────────────


def test_pyproject_is_valid_toml_with_correct_pins(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    content = (result.target_dir / 'pyproject.toml').read_text()
    parsed = tomllib.loads(content)
    assert parsed['project']['name'] == 'mi-saas'
    assert parsed['project']['requires-python'] == '>=3.12'
    deps = parsed['project']['dependencies']
    assert any(f'@v{CORE_VERSION}' in d for d in deps), deps
    # v1.1.1: default es HTTPS, no SSH
    assert any('git+https://' in d for d in deps), deps
    assert not any('git+ssh://' in d for d in deps), deps
    pkg_find = parsed['tool']['setuptools']['packages']['find']['include']
    assert 'mi_saas*' in pkg_find
    assert 'mi_saas_modulo*' in pkg_find


# ─── git_protocol flag (v1.1.1) ──────────────────────────────────────────


def test_default_git_protocol_is_https(tmp_path: Path) -> None:
    """Fricción de onboarding: HTTPS funciona con `gh auth setup-git`,
    SSH requiere que la key del usuario tenga acceso al org. El default
    debe ser el de menor fricción."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    assert result.git_protocol == 'https'
    pyproject = (result.target_dir / 'pyproject.toml').read_text()
    assert 'git+https://github.com/agentecopilotoai-code/copiloto-core.git' in pyproject
    assert 'git+ssh://git@github.com' not in pyproject.split('# si preferís SSH')[-1] \
        if '# si preferís SSH' in pyproject else True
    # El URL activo del pin es HTTPS
    assert f'"copiloto-core @ git+https://github.com/agentecopilotoai-code/copiloto-core.git@v{result.core_version}"' in pyproject


def test_git_protocol_ssh_renders_ssh_pin(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        git_protocol='ssh',
    )
    assert result.git_protocol == 'ssh'
    pyproject = (result.target_dir / 'pyproject.toml').read_text()
    assert f'"copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@v{result.core_version}"' in pyproject


def test_invalid_git_protocol_raises(tmp_path: Path) -> None:
    with pytest.raises(InvalidGitProtocolError):
        generate_project(
            project_name='mi-saas',
            target_dir=tmp_path / 'p',
            git_protocol='gopher',
        )


def test_main_py_imports_module_and_wires_branding(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    main_src = (result.target_dir / 'mi_saas' / 'main.py').read_text()
    assert 'from copiloto_core import BrandingConfig, create_app' in main_src
    assert 'from mi_saas_modulo import module as mi_saas_modulo_module' in main_src
    assert 'create_app(' in main_src
    assert 'product_name="mi-saas"' in main_src


def test_module_init_declares_coremodule(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    src = (result.target_dir / 'mi_saas_modulo' / '__init__.py').read_text()
    assert 'from copiloto_core import CoreModule' in src
    assert 'code="mi_saas_modulo"' in src
    assert '"mi_saas_modulo:read"' in src
    assert '"mi_saas_modulo:write"' in src
    assert '"migrations/001_init.sql"' in src


def test_module_routers_use_canonical_depends(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    src = (result.target_dir / 'mi_saas_modulo' / 'routers.py').read_text()
    # Patrón canónico documentado en docs/EXTENDING.md
    assert 'authenticate_request' in src
    assert 'require_capability' in src
    assert 'from copiloto_core.db.pool import db' in src


def test_migration_enables_rls(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    sql = (result.target_dir / 'mi_saas_modulo' / 'migrations' / '001_init.sql').read_text()
    assert 'create schema if not exists mi_saas_modulo' in sql
    assert 'tenant_id   uuid not null' in sql
    assert 'enable row level security' in sql
    assert "current_setting('app.current_tenant', true)::uuid" in sql


def test_env_example_has_critical_vars(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    env = (result.target_dir / '.env.example').read_text()
    # Variables sin las cuales el core no arranca
    for key in (
        'DATABASE_URL=', 'JWT_SECRET=', 'AUTH0_DOMAIN=', 'REDIS_URL=',
        'APP_NAME=mi-saas',
    ):
        assert key in env, f'falta en .env.example: {key}'


def test_gitignore_excludes_dotenv_but_not_example(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    gi = (result.target_dir / '.gitignore').read_text()
    assert '.env' in gi
    assert '!.env.example' in gi


def test_readme_mentions_quickstart_commands(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    readme = (result.target_dir / 'README.md').read_text()
    assert 'python -m copiloto_core migrate --module=mi_saas_modulo' in readme
    assert 'uvicorn mi_saas.main:app' in readme
    assert f'v{CORE_VERSION}' in readme


# ─── Generated project is sintácticamente importable ─────────────────────


def test_generated_main_compiles(tmp_path: Path) -> None:
    """El main.py generado debe ser sintácticamente Python válido.
    No lo ejecutamos (necesitaría DB+Auth0+etc) — solo compilamos AST.
    """
    import ast
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    for py_path in [
        result.target_dir / 'mi_saas' / 'main.py',
        result.target_dir / 'mi_saas' / '__init__.py',
        result.target_dir / 'mi_saas_modulo' / '__init__.py',
        result.target_dir / 'mi_saas_modulo' / 'routers.py',
    ]:
        ast.parse(py_path.read_text(), filename=str(py_path))


# ─── Result dataclass shape ──────────────────────────────────────────────


def test_generation_result_is_frozen(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    assert isinstance(result, GenerationResult)
    with pytest.raises(Exception):  # FrozenInstanceError
        result.project_name = 'otro'  # type: ignore[misc]


# ─── CLI dispatcher integration (__main__.py) ────────────────────────────


def test_cli_new_project_happy_path(tmp_path: Path, capsys) -> None:
    """E2E del subcomando: pasamos por argparse + dispatcher."""
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    rc = main([
        'new-project', 'demo-app',
        '--target-dir', str(target),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert 'demo-app' in out
    assert 'Próximos pasos' in out
    # Verificá que efectivamente escribió a disco
    assert (target / 'pyproject.toml').is_file()
    assert (target / 'demo_app' / 'main.py').is_file()
    assert (target / 'demo_app_modulo' / '__init__.py').is_file()


def test_cli_new_project_with_module_override(
    tmp_path: Path, capsys,
) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    rc = main([
        'new-project', 'demo-app',
        '--target-dir', str(target),
        '--module-name', 'alertas',
    ])
    assert rc == 0
    assert (target / 'alertas' / '__init__.py').is_file()
    assert not (target / 'demo_app_modulo').exists()


def test_cli_new_project_invalid_name_exits_2(
    tmp_path: Path, capsys,
) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    rc = main([
        'new-project', 'INVALID!NAME',
        '--target-dir', str(tmp_path / 'p'),
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert 'inválido' in err.lower() or 'invalid' in err.lower()


def test_cli_new_project_collision_exits_2(
    tmp_path: Path, capsys,
) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    target.mkdir()
    (target / 'archivo-previo.txt').write_text('hola')
    rc = main([
        'new-project', 'demo',
        '--target-dir', str(target),
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert 'ya existe' in err.lower()


def test_cli_new_project_git_protocol_ssh_flag(
    tmp_path: Path, capsys,
) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    rc = main([
        'new-project', 'demo',
        '--target-dir', str(target),
        '--git-protocol', 'ssh',
    ])
    assert rc == 0
    pyproject = (target / 'pyproject.toml').read_text()
    assert 'git+ssh://git@github.com' in pyproject
    assert capsys.readouterr().out.endswith  # smoke


def test_cli_new_project_invalid_git_protocol(
    tmp_path: Path, capsys,
) -> None:
    """argparse choices rechaza valores fuera de https|ssh con exit 2."""
    from copiloto_core.__main__ import main  # noqa: PLC0415

    with pytest.raises(SystemExit) as exc:
        main([
            'new-project', 'demo',
            '--target-dir', str(tmp_path / 'p'),
            '--git-protocol', 'gopher',
        ])
    assert exc.value.code == 2
    assert "invalid choice: 'gopher'" in capsys.readouterr().err
