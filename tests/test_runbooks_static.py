"""Static tests for TASK-0066 — Runbooks operacionales por incidente.

Coverage:
 1.  Existen los 9 runbooks declarados en el backlog.
 2.  Cada runbook tiene las 5 secciones mínimas (Síntoma, Diagnóstico,
     Mitigación inmediata, Fix definitivo, Post-mortem checklist).
 3.  Cada runbook supera un mínimo razonable de longitud (no es stub).
 4.  Cada regla en `infra/observability/alerts.yaml` declara `runbook_url`.
 5.  Cada `runbook_url` apunta a un archivo existente en el repo.
 6.  El README de runbooks lista todos los archivos creados.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
RUNBOOK_DIR = ROOT / 'docs' / 'runbooks'
ALERTS_YAML = ROOT / 'infra' / 'observability' / 'alerts.yaml'

EXPECTED_RUNBOOKS = (
    'meta-token-expired.md',
    'meta-quality-rating-dropped.md',
    'postgres-down.md',
    'rate-limit-meta-hit.md',
    'cloud-llm-rate-limited.md',
    'circuit-breaker-open-sustained.md',
    'worker-queue-backlog.md',
    'webhook-flood.md',
    'consent-violation-claim.md',
)

REQUIRED_SECTIONS = (
    '## Síntoma',
    '## Diagnóstico',
    '## Mitigación inmediata',
    '## Fix definitivo',
    '## Post-mortem checklist',
)


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_runbook_dir_exists() -> None:
    assert RUNBOOK_DIR.is_dir(), f"falta carpeta {RUNBOOK_DIR}"


@pytest.mark.parametrize('filename', EXPECTED_RUNBOOKS)
def test_each_expected_runbook_exists(filename: str) -> None:
    path = RUNBOOK_DIR / filename
    assert path.is_file(), f"falta runbook {filename}"


@pytest.mark.parametrize('filename', EXPECTED_RUNBOOKS)
def test_each_runbook_has_required_sections(filename: str) -> None:
    content = _read(RUNBOOK_DIR / filename)
    for section in REQUIRED_SECTIONS:
        assert section in content, (
            f"{filename} no incluye la sección '{section}'"
        )


@pytest.mark.parametrize('filename', EXPECTED_RUNBOOKS)
def test_each_runbook_has_minimum_length(filename: str) -> None:
    """Un runbook útil tiene ≥ 30 líneas no vacías y > 1200 caracteres.

    Esto bloquea stubs vacíos como "TBD" o "(pendiente)".
    """
    content = _read(RUNBOOK_DIR / filename)
    non_empty_lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(non_empty_lines) >= 30, (
        f"{filename} tiene solo {len(non_empty_lines)} líneas no vacías"
    )
    assert len(content) >= 1200, (
        f"{filename} mide {len(content)} chars (<1200, probable stub)"
    )


def test_runbooks_readme_lists_all_files() -> None:
    readme = RUNBOOK_DIR / 'README.md'
    assert readme.is_file(), "falta docs/runbooks/README.md"
    content = _read(readme)
    for filename in EXPECTED_RUNBOOKS:
        assert filename in content, (
            f"README de runbooks no menciona {filename}"
        )


def _parse_alert_rules(yaml_text: str) -> list[dict]:
    """Parser minimalista: extrae cada bloque `- alert: NAME` y sus campos.

    No depende de PyYAML para mantener el test estático libre de fixtures.
    Devuelve lista de dicts con keys: name, has_runbook_url, runbook_url.
    """
    rules: list[dict] = []
    current: dict | None = None
    in_annotations = False
    indent_alert = None
    for raw in yaml_text.splitlines():
        stripped = raw.lstrip()
        leading = len(raw) - len(stripped)
        if stripped.startswith('- alert:'):
            if current is not None:
                rules.append(current)
            name = stripped.split(':', 1)[1].strip()
            current = {'name': name, 'has_runbook_url': False, 'runbook_url': None}
            in_annotations = False
            indent_alert = leading
            continue
        if current is None:
            continue
        # Nueva sección top-level del grupo cierra la regla.
        if stripped.startswith('- name:') and indent_alert is not None and leading <= indent_alert:
            rules.append(current)
            current = None
            continue
        if stripped.startswith('annotations:'):
            in_annotations = True
            continue
        if stripped.startswith('labels:'):
            in_annotations = False
            continue
        if in_annotations:
            m = re.match(r'runbook_url:\s*(\S+)\s*$', stripped)
            if m:
                current['has_runbook_url'] = True
                current['runbook_url'] = m.group(1)
    if current is not None:
        rules.append(current)
    return rules


def test_alerts_yaml_exists() -> None:
    assert ALERTS_YAML.is_file(), f"falta {ALERTS_YAML}"


def test_every_alert_has_runbook_url() -> None:
    rules = _parse_alert_rules(_read(ALERTS_YAML))
    assert rules, "el parser no encontró ninguna regla en alerts.yaml"
    missing = [r['name'] for r in rules if not r['has_runbook_url']]
    assert not missing, (
        f"reglas sin runbook_url: {missing}"
    )


def test_runbook_url_points_to_existing_file() -> None:
    rules = _parse_alert_rules(_read(ALERTS_YAML))
    for rule in rules:
        url = rule['runbook_url']
        assert url, f"regla {rule['name']} sin runbook_url"
        target = ROOT / url
        assert target.is_file(), (
            f"runbook_url '{url}' de alerta {rule['name']} no existe"
        )


def test_runbook_dir_only_contains_markdown() -> None:
    """Higiene: solo .md en runbooks (no stubs, no archivos sueltos)."""
    for entry in RUNBOOK_DIR.iterdir():
        if entry.is_file():
            assert entry.suffix == '.md', f"archivo no .md en runbooks: {entry.name}"


def test_alert_rule_count_matches_expected() -> None:
    """Sentinel: si alguien añade alertas, este test obliga a documentar."""
    rules = _parse_alert_rules(_read(ALERTS_YAML))
    names = {r['name'] for r in rules}
    expected_minimum = {
        'HighOutboundErrorRate',
        'BotResponseLatencyP95High',
        'WorkerQueueBacklog',
        'CircuitBreakerOpenSustained',
        'SchedulerBehind',
        'BackupCloudStale',
        'BackupVerifyFailed',
        'OutboundDLQGrowing',
        'MetricsEndpointSilent',
    }
    missing = expected_minimum - names
    assert not missing, f"faltan alertas: {missing}"
