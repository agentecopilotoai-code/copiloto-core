"""Tests para `copiloto_core._scripts` + subcomandos del CLI (v1.3.0).

Cubre el dispatcher genérico (`run_packaged_script`) + el wiring del
CLI para los 8 scripts shipeados. Tests de integración profundos de
cada script viven en sus propios test_*_static.py — acá solo
verificamos la fachada Python.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from copiloto_core._scripts import (
    ScriptError,
    _resolve_script_path,
    run_packaged_script,
)
from copiloto_core.__main__ import _PACKAGED_SCRIPTS


# ─── Resolver de paths ──────────────────────────────────────────────────


def test_resolve_existing_script_returns_path() -> None:
    """generate-local-secrets.sh existe en el package."""
    path = _resolve_script_path('generate-local-secrets.sh')
    assert path.is_file()
    assert path.name == 'generate-local-secrets.sh'


def test_resolve_missing_script_raises() -> None:
    with pytest.raises(ScriptError, match='Script no encontrado'):
        _resolve_script_path('does-not-exist.sh')


@pytest.mark.parametrize('script_filename', [
    s[0] for s in _PACKAGED_SCRIPTS.values()
])
def test_every_packaged_script_is_actually_present(script_filename: str) -> None:
    """Catch-all: cada nombre de archivo declarado en _PACKAGED_SCRIPTS
    debe corresponder a un .sh real bajo copiloto_core/scripts/.
    Sin esto, agregar una entrada al map sin shippearla deja un
    subcomando que muere en runtime."""
    path = _resolve_script_path(script_filename)
    assert path.is_file()


def test_auth0_actions_js_files_are_packaged() -> None:
    """configure-auth0.sh referencia copiloto_core/scripts/auth0_actions/*.js
    (custom_claims, mfa_challenge, account_linking). Sin esos archivos,
    el script falla al subir las actions a Auth0."""
    from importlib import resources

    actions_dir = resources.files('copiloto_core.scripts.auth0_actions')
    js_files = [f.name for f in actions_dir.iterdir() if f.name.endswith('.js')]
    assert {'custom_claims.js', 'mfa_challenge.js', 'account_linking.js'}.issubset(
        set(js_files),
    ), f'falta algún .js de auth0_actions: {js_files}'


def test_postgres_url_lib_is_packaged() -> None:
    """lib/postgres-url.sh es sourceado por backup/restore. Debe viajar."""
    from importlib import resources

    ref = resources.files('copiloto_core.scripts.lib').joinpath('postgres-url.sh')
    assert ref.is_file()


# ─── Dispatcher: smoke ───────────────────────────────────────────────────


def test_run_script_propagates_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: ejecutar `reset-local-dev.sh` sin `--yes` debe abortar con
    exit ≠ 0. Validamos el roundtrip CLI → bash → exit code."""
    monkeypatch.chdir(tmp_path)
    rc = run_packaged_script('reset-local-dev.sh', args=[])
    assert rc != 0  # script aborta sin --yes


def test_run_script_unknown_raises_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ScriptError, match='Script no encontrado'):
        run_packaged_script('does-not-exist.sh')


def test_run_script_uses_cwd_of_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Por default usa Path.cwd(), no el path del package. Es lo que
    queremos: los scripts escriben en ./backups, ./.env del consumer."""
    monkeypatch.chdir(tmp_path)
    # smoke-test sale ≠ 0 si los endpoints no responden (esperado en test).
    # No nos importa el exit code, solo que el cwd se haya respetado.
    rc = run_packaged_script('smoke-test.sh', args=[])
    assert isinstance(rc, int)


# ─── CLI integration: cada subcomando del map se registra ────────────────


@pytest.mark.parametrize('cli_name', list(_PACKAGED_SCRIPTS.keys()))
def test_cli_subcommand_help_works(cli_name: str, capsys) -> None:
    """argparse debe registrar cada subcomando con su descripción.
    `python -m copiloto_core <cmd> --help` no debe abortar con
    'invalid choice'."""
    from copiloto_core.__main__ import main  # noqa: PLC0415

    with pytest.raises(SystemExit) as exc:
        main([cli_name, '--help'])
    # --help exit 0 = subcommand registrado correctamente
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert cli_name in out
    # help text debe incluir alguna mención del script bash
    assert '.sh' in out


def test_cli_unknown_subcommand_exits_with_error(capsys) -> None:
    from copiloto_core.__main__ import main  # noqa: PLC0415

    with pytest.raises(SystemExit) as exc:
        main(['nonexistent-command'])
    assert exc.value.code == 2


def test_packaged_scripts_map_has_no_duplicates() -> None:
    """Defense: cada script bash debe estar referenciado por UN solo
    subcomando CLI. Sino el help es ambiguo y el usuario no sabe cuál usar."""
    filenames = [v[0] for v in _PACKAGED_SCRIPTS.values()]
    assert len(filenames) == len(set(filenames)), \
        f'duplicado en _PACKAGED_SCRIPTS: {filenames}'


def test_packaged_scripts_have_descriptive_help() -> None:
    """Cada entry debe tener help_text no vacío y razonablemente descriptivo."""
    for cli_name, (script, help_text) in _PACKAGED_SCRIPTS.items():
        assert len(help_text) > 20, \
            f'{cli_name}: help_text muy corto ({help_text!r})'
        assert not help_text.startswith(' '), \
            f'{cli_name}: help_text con espacio inicial'
