"""Tests para `__main__._cmd_generate_secrets` (v1.3.1).

Handler Python-native que reemplaza CHANGE_ME en `.env` preservando
hostnames, project name, etc. — diferente del bash original que
generaba desde scratch con hostnames docker-internal.

Bug que cubre: el bash original ponía `@postgres:5432` (hostname
docker-internal) lo cual rompía bootstrap cuando el consumer corre
el CLI desde su host (donde `postgres` no resuelve).
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _run(argv: list[str]) -> int:
    from copiloto_core.__main__ import main  # noqa: PLC0415
    return main(argv)


# ─── Happy path: .env existe con CHANGE_ME ───────────────────────────────


def test_replaces_change_me_preserving_hostname(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """El bug original: bash overwrite con @postgres:. El handler nuevo
    debe preservar @localhost: (lo que el consumer puso)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'DATABASE_URL=postgres://copiloto_app:CHANGE_ME@localhost:5432/satguajira\n'
        'APP_DB_PASSWORD=CHANGE_ME\n'
        'JWT_SECRET=CHANGE_ME\n'
    )

    rc = _run(['generate-secrets'])
    assert rc == 0

    new_env = (tmp_path / '.env').read_text()
    # Hostname preservado
    assert '@localhost:5432/satguajira' in new_env
    # Project name preservado
    assert '/satguajira' in new_env
    # CHANGE_ME reemplazado
    assert 'CHANGE_ME' not in new_env


def test_jwt_secret_is_random_long_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('JWT_SECRET=CHANGE_ME\n')

    _run(['generate-secrets'])
    content = (tmp_path / '.env').read_text()
    # JWT_SECRET=<random>
    line = next(l for l in content.splitlines() if l.startswith('JWT_SECRET='))
    value = line.split('=', 1)[1]
    # 48 bytes random → ~64 chars base64-url
    assert len(value) >= 50, f'JWT muy corto: {len(value)} chars'
    assert value != 'CHANGE_ME'


def test_database_url_password_matches_app_db_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El password inline en DATABASE_URL debe ser EL MISMO que
    APP_DB_PASSWORD — sino bootstrap falla al conectar."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'DATABASE_URL=postgres://copiloto_app:CHANGE_ME@localhost:5432/db\n'
        'APP_DB_PASSWORD=CHANGE_ME\n'
    )

    _run(['generate-secrets'])
    content = (tmp_path / '.env').read_text()

    # Extraer APP_DB_PASSWORD
    pwd_line = next(l for l in content.splitlines()
                    if l.startswith('APP_DB_PASSWORD='))
    pwd = pwd_line.split('=', 1)[1]

    # El URL debe contener ese mismo password
    assert f'copiloto_app:{pwd}@' in content


def test_postgres_password_matches_admin_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'DATABASE_ADMIN_URL=postgres://postgres:CHANGE_ME@localhost:5432/db\n'
        'POSTGRES_PASSWORD=CHANGE_ME\n'
    )

    _run(['generate-secrets'])
    content = (tmp_path / '.env').read_text()
    pwd = next(l for l in content.splitlines()
               if l.startswith('POSTGRES_PASSWORD=')).split('=', 1)[1]
    assert f'postgres:{pwd}@' in content


def test_does_not_touch_non_change_me_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El user puede haber editado .env manualmente. Esos valores
    deben quedar intactos."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'JWT_SECRET=mi_secret_manual_no_lo_toques\n'
        'APP_DB_PASSWORD=CHANGE_ME\n'
        'APP_NAME=satguajira\n'
        'OBSERVABILITY_ALLOWED_IPS=127.0.0.1/32\n'
    )

    _run(['generate-secrets'])
    content = (tmp_path / '.env').read_text()
    assert 'JWT_SECRET=mi_secret_manual_no_lo_toques' in content
    assert 'APP_NAME=satguajira' in content
    assert 'OBSERVABILITY_ALLOWED_IPS=127.0.0.1/32' in content
    assert 'APP_DB_PASSWORD=CHANGE_ME' not in content


# ─── Bootstrap automático desde .env.example ─────────────────────────────


def test_creates_env_from_example_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env.example').write_text(
        'JWT_SECRET=CHANGE_ME\n'
        'APP_NAME=demo\n'
    )

    rc = _run(['generate-secrets'])
    assert rc == 0
    assert (tmp_path / '.env').exists()

    content = (tmp_path / '.env').read_text()
    assert 'APP_NAME=demo' in content
    assert 'CHANGE_ME' not in content


def test_errors_if_no_env_or_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = _run(['generate-secrets'])
    assert rc == 2
    err = capsys.readouterr().err
    assert '.env' in err and '.env.example' in err


# ─── Idempotencia ────────────────────────────────────────────────────────


def test_idempotent_no_change_me_remaining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('JWT_SECRET=CHANGE_ME\n')

    rc1 = _run(['generate-secrets'])
    after_first = (tmp_path / '.env').read_text()

    # Re-run
    rc2 = _run(['generate-secrets'])
    after_second = (tmp_path / '.env').read_text()

    assert rc1 == 0
    assert rc2 == 0
    # Segunda corrida no debe regenerar (no hay CHANGE_ME)
    assert after_first == after_second
    out = capsys.readouterr().out
    assert 'sin CHANGE_ME pendientes' in out or 'Nada para regenerar' in out


# ─── Permisos ────────────────────────────────────────────────────────────


def test_env_file_is_chmod_600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin esto cualquier otro user del sistema podría leer las passwords."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('JWT_SECRET=CHANGE_ME\n')

    _run(['generate-secrets'])
    mode = (tmp_path / '.env').stat().st_mode & 0o777
    assert mode == 0o600, f'.env debe ser 600, es {oct(mode)}'


# ─── Regression: no usar hostnames docker-internal ──────────────────────


def test_never_writes_postgres_hostname_to_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1.3.1 fix: el bash original escribía `@postgres:5432/copilotoia`
    (hostname docker-internal). El handler Python debe respetar lo que
    haya en el .env existente."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'DATABASE_URL=postgres://copiloto_app:CHANGE_ME@localhost:5432/mi_db\n'
        'APP_DB_PASSWORD=CHANGE_ME\n'
    )

    _run(['generate-secrets'])
    content = (tmp_path / '.env').read_text()
    # No debe haber inyectado el hostname docker
    assert '@postgres:' not in content
    assert '@localhost:' in content
    # Y el db name debe preservarse
    assert '/mi_db' in content
    assert '/copilotoia' not in content


def test_scaffolder_env_example_has_postgres_password() -> None:
    """v1.3.1: el .env.example generado por new-project debe tener
    POSTGRES_PASSWORD como key explícita, sino generate-secrets no
    puede asignarle un valor consistente con DATABASE_ADMIN_URL."""
    from copiloto_core.scaffolding import _ENV_EXAMPLE  # noqa: PLC0415

    template = _ENV_EXAMPLE.format(
        project_name='demo', project_package='demo',
    )
    assert 'POSTGRES_PASSWORD=CHANGE_ME' in template
    assert 'S3_SECRET_ACCESS_KEY=CHANGE_ME' in template
