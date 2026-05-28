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
        'templates/landing.html',          # v1.5.0
        'templates/dashboard.html',        # v1.5.0
        'mi_saas_modulo/__init__.py',
        'mi_saas_modulo/routers.py',
        'mi_saas_modulo/migrations/001_init.sql',
    }
    assert set(result.files_written) == expected
    for rel in expected:
        assert (result.target_dir / rel).is_file(), f'missing: {rel}'


# ─── v1.5.0: landing + dashboard ────────────────────────────────────────


def test_landing_html_uses_project_name(tmp_path: Path) -> None:
    result = generate_project(project_name='mi-saas', target_dir=tmp_path / 'p')
    html = (result.target_dir / 'templates' / 'landing.html').read_text()
    assert '<title>mi-saas</title>' in html
    assert 'id="product-name">mi-saas</h1>' in html
    # Botón de login al flow del core
    assert 'href="/admin/login"' in html
    assert 'Iniciar sesión' in html
    # Fetch del branding del core
    assert "fetch('/v1/branding')" in html


def test_dashboard_html_is_auth_required_via_session_fetch(tmp_path: Path) -> None:
    result = generate_project(project_name='mi-saas', target_dir=tmp_path / 'p')
    html = (result.target_dir / 'templates' / 'dashboard.html').read_text()
    # Fetch a /admin/api/session — si falla, redirect a /
    assert "fetch('/admin/api/session')" in html
    assert "window.location.href = '/'" in html
    # Botón de logout
    assert "fetch('/admin/logout'" in html


def test_main_py_wires_landing_and_dashboard_handlers(tmp_path: Path) -> None:
    result = generate_project(project_name='mi-saas', target_dir=tmp_path / 'p')
    main_src = (result.target_dir / 'mi_saas' / 'main.py').read_text()
    # Handlers nuevos
    assert "@app.get('/'," in main_src or '@app.get("/"' in main_src
    assert "@app.get('/dashboard'" in main_src or '@app.get("/dashboard"' in main_src
    # Dashboard auth-gated
    assert 'Depends(authenticate_request)' in main_src
    # Lee templates desde disco
    assert "_LANDING_HTML" in main_src
    assert "_DASHBOARD_HTML" in main_src
    # admin_panel NO se activa por default (comentado)
    assert '# admin_panel=True' in main_src


def test_main_py_compiles_to_ast(tmp_path: Path) -> None:
    """v1.5.0: main.py se hizo más grande con landing+dashboard.
    Confirmamos que sigue siendo Python sintácticamente válido."""
    import ast  # noqa: PLC0415
    result = generate_project(project_name='mi-saas', target_dir=tmp_path / 'p')
    main_path = result.target_dir / 'mi_saas' / 'main.py'
    ast.parse(main_path.read_text(), filename=str(main_path))


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
    # v1.5.0: el import combina BrandingConfig + create_app + authenticate_request
    # en un solo `from copiloto_core import (...)` multi-línea.
    assert 'BrandingConfig' in main_src
    assert 'create_app' in main_src
    assert 'from copiloto_core import' in main_src
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
    # Variables sin las cuales el core no arranca.
    # v1.5.5: AUTH0_* removidos del .env.example — viven en
    # .env.auth0.local (auto-generado por auth0-configure).
    for key in (
        'DATABASE_URL=', 'JWT_SECRET=', 'REDIS_URL=',
        'APP_NAME=mi-saas',
    ):
        assert key in env, f'falta en .env.example: {key}'
    # Anti-pattern: AUTH0_MGMT_CLIENT_* NUNCA debe estar como key
    # en .env (son credentials de "Capa 3" que viven solo en shell).
    assert 'AUTH0_MGMT_CLIENT_ID=' not in env
    assert 'AUTH0_MGMT_CLIENT_SECRET=' not in env
    # AUTH0_DOMAIN tampoco — lo escribe auth0-configure en .env.auth0.local
    assert 'AUTH0_DOMAIN=' not in env
    assert 'AUTH0_API_AUDIENCE=' not in env


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


# ─── --with-infra flag (v1.2.0) ──────────────────────────────────────────


def test_with_infra_includes_docker_compose_and_scripts(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
    )
    assert result.with_infra is True
    assert 'docker-compose.yml' in result.files_written
    assert 'scripts/dev-up.sh' in result.files_written
    assert '.secrets/.gitkeep' in result.files_written


def test_without_infra_does_not_include_infra_files(tmp_path: Path) -> None:
    """Default (sin flag) NO genera docker-compose ni dev-up.sh —
    compat con v1.1.x para quien ya tiene su propio stack."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    assert result.with_infra is False
    assert 'docker-compose.yml' not in result.files_written
    assert 'scripts/dev-up.sh' not in result.files_written


def test_docker_compose_uses_project_db_name(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
    )
    compose = (result.target_dir / 'docker-compose.yml').read_text()
    # Postgres DB name = project_package (snake_case)
    assert 'POSTGRES_DB: mi_saas' in compose
    assert 'pgvector/pgvector:pg16' in compose
    assert 'redis:7-alpine' in compose
    assert 'minio/minio' in compose
    # Ports exportados a localhost
    assert '"5432:5432"' in compose
    assert '"6379:6379"' in compose


def test_dev_up_script_is_executable(tmp_path: Path) -> None:
    """Sin x-bit, el usuario tiene que `chmod +x` antes de correrlo —
    una fuente más de fricción que el scaffolder evita."""
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
    )
    script = result.target_dir / 'scripts' / 'dev-up.sh'
    mode = script.stat().st_mode & 0o777
    assert mode & 0o100, f'scripts/dev-up.sh debería ser ejecutable, mode={oct(mode)}'


def test_dev_up_script_invokes_bootstrap_and_migrate(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
        module_name='alertas',
    )
    src = (result.target_dir / 'scripts' / 'dev-up.sh').read_text()
    assert 'docker compose up -d' in src
    assert 'python -m copiloto_core bootstrap --create-app-user' in src
    assert 'python -m copiloto_core migrate --module=alertas' in src
    assert 'uvicorn mi_saas.main:app' in src


def test_dev_up_script_does_not_source_env(tmp_path: Path) -> None:
    """v1.2.1: el script NO debe hacer `source .env` — eso rompe con
    cualquier sintaxis bash-incompatible (paréntesis en comentarios,
    etc.). El CLI ya carga .env via python-dotenv."""
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
    )
    src = (result.target_dir / 'scripts' / 'dev-up.sh').read_text()
    assert 'source .env' not in src
    assert 'source ./.env' not in src


def test_cli_new_project_with_infra_flag(tmp_path: Path, capsys) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    rc = main([
        'new-project', 'demo',
        '--target-dir', str(target),
        '--with-infra',
    ])
    assert rc == 0
    assert (target / 'docker-compose.yml').is_file()
    assert (target / 'scripts' / 'dev-up.sh').is_file()
    out = capsys.readouterr().out
    assert 'dev-up.sh' in out


# ─── --prod-ready flag (v2.1.0 — Production Deployment Kit) ─────────────


def test_prod_ready_includes_all_deployment_artifacts(tmp_path: Path) -> None:
    """`--prod-ready` agrega 8 archivos para deploy a producción.
    Test único que valida la presencia de todos juntos — los tests
    siguientes verifican el contenido específico de cada uno."""
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        prod_ready=True,
    )
    assert result.prod_ready is True
    expected = {
        'Dockerfile',
        '.dockerignore',
        'docker-compose.prod.yml',
        'gunicorn_conf.py',
        'nginx.conf.example',
        'scripts/backup.sh',
        '.github/workflows/deploy.yml',
        '.env.prod.example',
    }
    missing = expected - set(result.files_written)
    assert not missing, f'falta(n) artefacto(s) prod: {missing}'


def test_without_prod_ready_does_not_include_deployment_artifacts(
    tmp_path: Path,
) -> None:
    """Default (sin flag) NO genera prod kit — compat con v2.0.x donde
    el consumer escribía sus propios artefactos de deploy."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p',
    )
    assert result.prod_ready is False
    for path in (
        'Dockerfile', 'docker-compose.prod.yml', 'gunicorn_conf.py',
        'nginx.conf.example', '.github/workflows/deploy.yml',
    ):
        assert path not in result.files_written, f'{path} no debería estar'


def test_prod_ready_combinable_with_with_infra(tmp_path: Path) -> None:
    """Los dos flags son ortogonales: dev compose para iterar local,
    prod compose para deploy. Ambos se generan, no se pisan."""
    result = generate_project(
        project_name='mi-saas',
        target_dir=tmp_path / 'p',
        with_infra=True,
        prod_ready=True,
    )
    assert 'docker-compose.yml' in result.files_written       # dev
    assert 'docker-compose.prod.yml' in result.files_written  # prod
    assert 'scripts/dev-up.sh' in result.files_written        # dev
    assert 'scripts/backup.sh' in result.files_written        # prod


def test_dockerfile_is_multistage_with_non_root_user(tmp_path: Path) -> None:
    """Security posture: multi-stage (slim runtime) + USER no-root +
    healthcheck. Estos 3 son requisitos no-negociables del core."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    docker = (result.target_dir / 'Dockerfile').read_text()
    # Multi-stage
    assert 'AS builder' in docker
    assert 'AS runtime' in docker
    # Non-root user (UID 10001 evita colisión con usuarios del host)
    assert 'useradd' in docker
    assert 'USER app' in docker
    assert '--uid 10001' in docker
    # Healthcheck embebido apunta a /v1/livez (NO touches DB).
    assert 'HEALTHCHECK' in docker
    assert '/v1/livez' in docker
    # tini como PID 1 para reap zombies + signal propagation
    assert 'tini' in docker


def test_docker_compose_prod_has_healthchecks_and_restart_always(
    tmp_path: Path,
) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    compose = (result.target_dir / 'docker-compose.prod.yml').read_text()
    # restart: always en TODOS los services (no `unless-stopped` como dev)
    assert compose.count('restart: always') >= 4  # app + postgres + redis + minio
    # healthchecks
    assert 'healthcheck:' in compose
    assert '/v1/readyz' in compose  # app healthcheck usa readyz (toca DB+Redis)
    assert 'pg_isready' in compose
    assert 'redis-cli' in compose
    # App bindea a loopback (nginx en el host hace TLS)
    assert '127.0.0.1:8000:8000' in compose
    # Postgres + Redis NO exponen puertos al host (solo internal network)
    assert '"5432:5432"' not in compose
    assert '"6379:6379"' not in compose
    # Resource limits (deploy.resources.limits.memory)
    assert 'limits:' in compose
    assert 'memory: 1G' in compose  # app limit
    # Logging con rotation (evita disco lleno)
    assert 'max-size: "10m"' in compose
    # Volúmenes nombrados (no anónimos — sobreviven docker compose down -v)
    assert 'name: mi_saas_postgres' in compose


def test_docker_compose_prod_requires_secrets_via_env_with_error(
    tmp_path: Path,
) -> None:
    """Los `${VAR:?msg}` de compose hacen fail-fast si el operador
    olvidó setear una variable obligatoria — mejor que arrancar con
    password vacío y descubrirlo en runtime."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    compose = (result.target_dir / 'docker-compose.prod.yml').read_text()
    assert 'POSTGRES_PASSWORD:?' in compose
    assert 'REDIS_PASSWORD:?' in compose
    assert 'S3_ACCESS_KEY_ID:?' in compose
    assert 'S3_SECRET_ACCESS_KEY:?' in compose


def test_gunicorn_conf_uses_uvicorn_worker_class(tmp_path: Path) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    conf = (result.target_dir / 'gunicorn_conf.py').read_text()
    assert "worker_class = 'uvicorn.workers.UvicornWorker'" in conf
    # WEB_CONCURRENCY env override (12-factor)
    assert "os.environ.get('WEB_CONCURRENCY'" in conf
    # max_requests + jitter para reciclar workers (anti-leak)
    assert 'max_requests' in conf
    assert 'max_requests_jitter' in conf
    # forwarded_allow_ips para confiar X-Forwarded-* del proxy
    assert 'forwarded_allow_ips' in conf


def test_nginx_conf_has_tls_security_headers_and_metrics_deny(
    tmp_path: Path,
) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    nginx = (result.target_dir / 'nginx.conf.example').read_text()
    # TLS via Let's Encrypt
    assert 'ssl_certificate' in nginx
    assert 'TLSv1.2 TLSv1.3' in nginx
    # Security headers
    assert 'Strict-Transport-Security' in nginx
    assert 'X-Content-Type-Options' in nginx
    assert 'X-Frame-Options' in nginx
    # /metrics solo accesible internamente
    assert 'location /metrics' in nginx
    assert 'deny all' in nginx
    # Rate limit en /admin/login (anti-brute)
    assert 'limit_req zone=app_login' in nginx
    # Forwarded headers al upstream (gunicorn las consume)
    assert 'X-Forwarded-For' in nginx
    assert 'X-Forwarded-Proto' in nginx


def test_backup_script_is_executable_and_uses_pg_dump_custom_format(
    tmp_path: Path,
) -> None:
    """Custom format (-Fc) es el único que permite pg_restore parcial
    (un solo schema, una sola tabla, sin DROP existentes, etc.)."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    script = result.target_dir / 'scripts' / 'backup.sh'
    mode = script.stat().st_mode & 0o777
    assert mode & 0o100, f'backup.sh debería ser ejecutable, mode={oct(mode)}'
    src = script.read_text()
    assert 'pg_dump' in src
    assert '-Fc' in src    # custom format
    assert 'pg_restore --list' in src  # integrity check
    assert 'RETENTION_DAYS' in src
    assert 'mtime' in src  # rotación por edad
    # Opcional S3 (puede estar comentado/condicional pero referenciado)
    assert 'S3_BUCKET' in src


def test_github_actions_deploy_builds_and_pushes_to_ghcr(
    tmp_path: Path,
) -> None:
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    wf = (result.target_dir / '.github' / 'workflows' / 'deploy.yml').read_text()
    assert 'ghcr.io' in wf
    assert 'docker/build-push-action' in wf
    # Triggers
    assert 'workflow_dispatch:' in wf
    # SSH deploy con migrate antes del up
    assert 'appleboy/ssh-action' in wf
    assert 'python -m copiloto_core migrate' in wf
    # Health check post-deploy (rollback manual si falla)
    assert '/v1/readyz' in wf


def test_env_prod_example_uses_docker_service_names(tmp_path: Path) -> None:
    """En prod las URLs apuntan a los nombres de servicio del compose
    (postgres, redis, minio), NO a localhost — los containers se
    resuelven por DNS interno de la network del compose."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    env = (result.target_dir / '.env.prod.example').read_text()
    assert '@postgres:5432' in env  # NO localhost
    assert '@redis:6379' in env
    assert 'http://minio:9000' in env
    # MFA SIEMPRE ON en prod
    assert 'MFA_ENFORCEMENT_ENABLED=true' in env
    # ENV=production gating
    assert 'ENV=production' in env


def test_dockerignore_excludes_dev_artifacts(tmp_path: Path) -> None:
    """.dockerignore debe excluir .venv, .env (real), tests/ y docs/
    para que la imagen final sea chica y no leakee secrets."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    di = (result.target_dir / '.dockerignore').read_text()
    for entry in ('.venv', '.env', 'tests/', 'docs/', '__pycache__', '.git'):
        assert entry in di, f'.dockerignore debería excluir {entry!r}'
    # .env.example SÍ se incluye (es el template, no tiene secrets reales)
    assert '!.env.example' in di


def test_gitignore_excludes_prod_backups_and_logs(tmp_path: Path) -> None:
    """v2.1.0 extiende .gitignore para dumps + logs del kit prod."""
    result = generate_project(
        project_name='mi-saas', target_dir=tmp_path / 'p', prod_ready=True,
    )
    gi = (result.target_dir / '.gitignore').read_text()
    assert '*.dump' in gi
    assert 'logs/' in gi
    assert '*.log' in gi


def test_cli_new_project_with_prod_ready_flag(tmp_path: Path, capsys) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    target = tmp_path / 'demo'
    rc = main([
        'new-project', 'demo',
        '--target-dir', str(target),
        '--prod-ready',
    ])
    assert rc == 0
    assert (target / 'Dockerfile').is_file()
    assert (target / 'docker-compose.prod.yml').is_file()
    assert (target / 'gunicorn_conf.py').is_file()
    out = capsys.readouterr().out
    assert 'Dockerfile' in out
    assert 'docker-compose.prod.yml' in out
