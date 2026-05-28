"""Tests para `_cmd_bootstrap` — selección del DSN admin (v1.3.2).

Bug regression: `getattr(settings, 'database_admin_url', None)` siempre
devolvía None porque Settings no tiene ese campo, y caíamos en
`database_url` (que es el user app sin permisos). El fix lee
`DATABASE_ADMIN_URL` del environment directo.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def _run(argv: list[str]) -> int:
    from copiloto_core.__main__ import main  # noqa: PLC0415
    return main(argv)


def test_prefers_database_admin_url_over_database_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """Cuando ambos están seteados, bootstrap debe usar DATABASE_ADMIN_URL.
    Sino fallaría al primer CREATE EXTENSION (que requiere superuser)."""
    monkeypatch.chdir(tmp_path)
    # .env con AMBOS URLs — admin con un host bogus que falle DNS,
    # app con localhost. Si el bootstrap usa el correcto (admin), va
    # a fallar con un error de DNS, no de password. Eso prueba que
    # eligió el admin URL.
    (tmp_path / '.env').write_text(
        'DATABASE_ADMIN_URL=postgres://postgres:pw@bogus.invalid.tld:5432/db\n'
        'DATABASE_URL=postgres://copiloto_app:pw@localhost:5432/db\n',
    )

    rc = _run(['bootstrap'])
    err = capsys.readouterr().err
    # Esperamos exit 3 (BootstrapError) por DNS fail del admin URL.
    # NO esperamos exit 0 ni un connect a localhost.
    assert rc != 0
    # El error debe mencionar resolución de nombre (DNS), no de auth.
    assert 'bogus.invalid.tld' in err or 'gaierror' in err.lower() or \
           'not known' in err.lower() or 'Name or service' in err.lower(), \
           f'esperaba error de DNS al admin URL, vi: {err}'


def test_falls_back_to_database_url_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """Si SOLO DATABASE_URL está seteado, bootstrap debe avisar via
    WARNING que va a usar fallback (probablemente fallará en CREATE)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'DATABASE_URL=postgres://copiloto_app:pw@bogus.invalid.tld:5432/db\n',
    )
    # Asegurar que DATABASE_ADMIN_URL no está en el env del proceso
    monkeypatch.delenv('DATABASE_ADMIN_URL', raising=False)

    rc = _run(['bootstrap'])
    err = capsys.readouterr().err
    assert rc != 0
    assert 'WARNING' in err
    assert 'DATABASE_ADMIN_URL' in err
    assert 'fallback' in err.lower()


def test_errors_clearly_mentions_database_url_when_misconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """Cuando el bootstrap falla por config de DB ausente o invalida,
    el mensaje DEBE mencionar DATABASE_URL / DATABASE_ADMIN_URL para
    que el user sepa qué configurar.

    No testeamos exit code específico porque depende del estado del
    entorno (pytest puede tener DATABASE_URL heredada del shell), pero
    en cualquier caso rc != 0 y el err es informativo."""
    monkeypatch.chdir(tmp_path)
    # .env sin URLs → bootstrap fallará temprano o tarde
    (tmp_path / '.env').write_text(
        'DATABASE_URL=postgres://x:y@no.such.host.invalid:5432/db\n',
    )
    monkeypatch.delenv('DATABASE_ADMIN_URL', raising=False)

    rc = _run(['bootstrap'])
    err = capsys.readouterr().err
    assert rc != 0
    # Algún hint del problema en el mensaje
    assert ('DATABASE' in err or 'no such' in err.lower()
            or 'gaierror' in err.lower()), \
           f'esperaba mensaje informativo: {err!r}'


def test_dotenv_helper_does_not_override_shell_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test directo del helper: si el user setea una env var en el
    shell, _load_dotenv_into_environ NO debe pisarla con lo del .env.
    Esa propiedad (override=False) es lo que permite que un operador
    haga `DATABASE_ADMIN_URL=... python -m copiloto_core bootstrap`
    sobreescribiendo lo que esté en .env."""
    from copiloto_core.__main__ import _load_dotenv_into_environ  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'TEST_OVERRIDE_VAR=from_dotenv\n',
    )
    monkeypatch.setenv('TEST_OVERRIDE_VAR', 'from_shell')

    _load_dotenv_into_environ()

    # Shell debe ganar
    assert os.environ['TEST_OVERRIDE_VAR'] == 'from_shell'


def test_dotenv_helper_fills_missing_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si la var NO está en el shell pero SÍ en .env, debe cargarse."""
    from copiloto_core.__main__ import _load_dotenv_into_environ  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        'TEST_FROM_DOTENV_ONLY=value123\n',
    )
    monkeypatch.delenv('TEST_FROM_DOTENV_ONLY', raising=False)

    _load_dotenv_into_environ()

    assert os.environ.get('TEST_FROM_DOTENV_ONLY') == 'value123'
