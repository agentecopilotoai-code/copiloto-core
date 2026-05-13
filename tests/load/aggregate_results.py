"""TASK-0072 — Aggregate Locust CSV output and regenerate `docs/sla.md`.

Locust exports `<prefix>_stats.csv` and `<prefix>_stats_history.csv`. We parse
the aggregated stats CSV (one row per request name + one `Aggregated` row),
extract p50/p95/p99 + RPS, and rewrite the *Resultado del último load test*
section of `docs/sla.md` so the doc is always in sync with the latest run.

Usage::

    python -m tests.load.aggregate_results \\
        --csv-prefix tests/load/results/run \\
        --sla-file docs/sla.md \\
        --enforce-sla

With ``--enforce-sla`` the script exits with status 1 if the aggregated p95
exceeds the configured target or the sustained RPS is below it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Iterable


SLA_SECTION_RE = re.compile(
    r'<!-- load-test-results:start -->.*?<!-- load-test-results:end -->',
    re.DOTALL,
)


def _read_stats(csv_prefix: Path) -> list[dict[str, str]]:
    stats_path = csv_prefix.parent / f'{csv_prefix.name}_stats.csv'
    if not stats_path.is_file():
        raise SystemExit(f'Locust stats CSV not found: {stats_path}')
    with stats_path.open(encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def _pick_aggregate(rows: Iterable[dict[str, str]]) -> dict[str, str]:
    for row in rows:
        if row.get('Name', '').strip().lower() == 'aggregated':
            return row
    raise SystemExit('Aggregated row missing from Locust stats CSV')


def _fmt_ms(value: str) -> str:
    if not value:
        return 'n/a'
    try:
        return f'{float(value):.0f} ms'
    except (TypeError, ValueError):
        return 'n/a'


def _fmt_rps(value: str) -> str:
    if not value:
        return 'n/a'
    try:
        return f'{float(value):.2f} req/s'
    except (TypeError, ValueError):
        return 'n/a'


def _render_table(rows: list[dict[str, str]]) -> str:
    headers = ['Endpoint', 'Reqs', 'Fails', 'RPS', 'p50', 'p95', 'p99', 'avg']
    lines = ['| ' + ' | '.join(headers) + ' |',
             '|' + '|'.join(['---'] * len(headers)) + '|']
    for row in rows:
        name = row.get('Name', '').strip()
        if not name:
            continue
        lines.append(
            '| ' + ' | '.join([
                name,
                row.get('Request Count', '0'),
                row.get('Failure Count', '0'),
                _fmt_rps(row.get('Requests/s', '')),
                _fmt_ms(row.get('50%', '')),
                _fmt_ms(row.get('95%', '')),
                _fmt_ms(row.get('99%', '')),
                _fmt_ms(row.get('Average Response Time', '')),
            ]) + ' |',
        )
    return '\n'.join(lines)


def _render_section(rows: list[dict[str, str]], aggregate: dict[str, str]) -> str:
    now = dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')
    sustained_rps = _fmt_rps(aggregate.get('Requests/s', ''))
    p50 = _fmt_ms(aggregate.get('50%', ''))
    p95 = _fmt_ms(aggregate.get('95%', ''))
    p99 = _fmt_ms(aggregate.get('99%', ''))
    fails = aggregate.get('Failure Count', '0')
    return '\n'.join([
        '<!-- load-test-results:start -->',
        f'**Última corrida:** {now}',
        '',
        f'- **RPS sostenido:** {sustained_rps}',
        f'- **p50 / p95 / p99 (agregado):** {p50} / {p95} / {p99}',
        f'- **Errores totales:** {fails}',
        '',
        '**Desglose por endpoint:**',
        '',
        _render_table(rows),
        '<!-- load-test-results:end -->',
    ])


def _update_sla_file(sla_path: Path, section: str) -> None:
    if not sla_path.is_file():
        raise SystemExit(f'SLA doc missing: {sla_path}')
    original = sla_path.read_text(encoding='utf-8')
    if not SLA_SECTION_RE.search(original):
        raise SystemExit(
            f'SLA doc {sla_path} does not contain the load-test-results markers',
        )
    updated = SLA_SECTION_RE.sub(section, original)
    sla_path.write_text(updated, encoding='utf-8')


def _enforce_sla(aggregate: dict[str, str], p95_target_ms: float, rps_target: float) -> int:
    failures = []
    try:
        p95 = float(aggregate.get('95%', '') or 0)
    except ValueError:
        p95 = 0.0
    try:
        rps = float(aggregate.get('Requests/s', '') or 0)
    except ValueError:
        rps = 0.0
    if p95 > p95_target_ms:
        failures.append(f'p95 {p95:.0f}ms > target {p95_target_ms:.0f}ms')
    if rps < rps_target:
        failures.append(f'sustained RPS {rps:.2f} < target {rps_target:.2f}')
    if failures:
        print('SLA enforcement failed:', file=sys.stderr)
        for line in failures:
            print(f'  - {line}', file=sys.stderr)
        return 1
    print(f'SLA met: p95={aggregate.get("95%", "?")}ms RPS={aggregate.get("Requests/s", "?")}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv-prefix', required=True, type=Path,
                        help='Locust --csv prefix (without _stats.csv suffix)')
    parser.add_argument('--sla-file', type=Path,
                        default=Path('docs') / 'sla.md')
    parser.add_argument('--enforce-sla', action='store_true')
    parser.add_argument('--p95-target-ms', type=float, default=2000.0)
    parser.add_argument('--rps-target', type=float, default=25.0)
    args = parser.parse_args(argv)

    rows = _read_stats(args.csv_prefix)
    aggregate = _pick_aggregate(rows)
    section = _render_section(rows, aggregate)
    _update_sla_file(args.sla_file, section)

    if args.enforce_sla:
        return _enforce_sla(aggregate, args.p95_target_ms, args.rps_target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
