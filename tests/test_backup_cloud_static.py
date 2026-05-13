"""Static tests for TASK-0064 — Backups automatizados a cloud + verificación.

Coverage (≥ 10 tests):
 1.  Schema declara `app.backup_runs` con columnas y CHECKs requeridos.
 2.  Schema declara índices de `backup_runs` para queries por fecha y kind.
 3.  `operator_alerts` admite `kind='backup_failure'` y permite tenant null
     sólo para ese kind.
 4.  `backup-to-cloud.sh` usa `pg_dump --format=custom`, cifra con GPG y sube a
     S3 con un path validado (regex anti-typo).
 5.  `backup-to-cloud.sh` actualiza `app.backup_runs` (running → ok | failed) y
     escribe sha256/size/duration.
 6.  `backup-to-cloud.sh` aplica la política 30 daily + monthly snapshot el
     día 01 y no toca el prefijo `monthly/`.
 7.  `verify-backup.sh` baja el dump, corre los 3 sanity checks y deja una
     fila en `audit_logs(action='backup.verified')`.
 8.  `verify-backup.sh` emite `operator_alerts(kind='backup_failure')` cuando
     falla, sin tenant_id.
 9.  `docker-compose.yml` declara el servicio `backup-worker` con profile
     `backups` y monta scripts + secrets.
10.  `infra/backup-worker/crontab` schedule diario 03:00 UTC + verify
     semanal 04:00 UTC domingo.
11.  Alerts.yaml define `BackupCloudStale` y `BackupVerifyFailed` con
     `runbook_url`.
12.  `docs/backup-policy.md` documenta RPO, restore y rotación de la clave
     GPG.
13.  Los dos scripts pasan `bash -n` (sintaxis válida).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _schema() -> str:
    return (ROOT / 'infra' / 'postgres' / '01-schema.sql').read_text(encoding='utf-8')


def _backup_script() -> str:
    return (ROOT / 'scripts' / 'backup-to-cloud.sh').read_text(encoding='utf-8')


def _verify_script() -> str:
    return (ROOT / 'scripts' / 'verify-backup.sh').read_text(encoding='utf-8')


def _compose() -> str:
    return (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')


def _alerts() -> dict:
    yaml = pytest.importorskip('yaml')
    return yaml.safe_load((ROOT / 'infra' / 'observability' / 'alerts.yaml').read_text(encoding='utf-8'))


def test_backup_runs_table_has_required_columns_and_checks() -> None:
    schema = _schema()
    assert 'create table app.backup_runs' in schema
    for column in (
        'id uuid primary key',
        'kind text not null default \'cloud_dump\'',
        'started_at timestamptz not null default now()',
        'finished_at timestamptz',
        'status text not null default \'running\'',
        'sha256 text',
        'size_bytes bigint',
        'duration_seconds numeric(10,3)',
        'evidence_path text',
        'error text',
        'metadata jsonb not null default',
    ):
        assert column in schema, f'missing column declaration: {column!r}'
    assert "check (kind in ('cloud_dump','cloud_verify'))" in schema
    assert "check (status in ('running','ok','failed'))" in schema


def test_backup_runs_indexes_present() -> None:
    schema = _schema()
    assert 'create index ix_backup_runs_started on app.backup_runs(started_at desc)' in schema
    assert 'create index ix_backup_runs_kind_status on app.backup_runs(kind, status, started_at desc)' in schema


def test_operator_alerts_supports_system_wide_backup_failure() -> None:
    schema = _schema()
    # New enum value reachable.
    assert "kind in ('negative_feedback','complaint','backup_failure','outbound_dlq_threshold')" in schema
    # Composite constraint: only `backup_failure` may have null tenant_id.
    assert 'chk_operator_alerts_system_alerts_have_no_tenant' in schema
    assert "(kind = 'backup_failure') or (tenant_id is not null)" in schema
    # tenant_id column itself is no longer NOT NULL (system alerts allowed).
    assert 'tenant_id uuid references app.tenants(id) on delete cascade' in schema


def test_backup_script_uses_pgdump_custom_and_encrypts_with_gpg() -> None:
    script = _backup_script()
    assert 'pg_dump "$DATABASE_ADMIN_URL" --format=custom' in script
    assert 'gpg --batch --yes --trust-model always' in script
    assert '--recipient "$BACKUP_GPG_RECIPIENT"' in script
    assert '--encrypt "$DUMP_PATH"' in script
    # S3 path validated by regex to catch typos at the bucket/env layer.
    assert "if [[ ! \"$S3_URI\" =~ ^s3://" in script
    assert 'db\\.dump\\.gpg$' in script
    assert 'sha256sum "$ENC_PATH"' in script
    assert 'aws "${AWS_CLI_ARGS[@]}" s3 cp "$ENC_PATH" "$S3_URI"' in script


def test_backup_script_records_backup_runs_lifecycle() -> None:
    script = _backup_script()
    assert "insert into app.backup_runs" in script
    assert "'running'" in script
    assert "set status='ok'" in script
    assert "set status='failed'" in script
    assert "sha256='${SHA256_HEX}'" in script
    assert 'size_bytes=${SIZE_BYTES}' in script
    assert 'duration_seconds=${DURATION}' in script


def test_backup_script_retention_30days_plus_monthly_snapshot() -> None:
    script = _backup_script()
    # Monthly snapshot copy on day 01.
    assert 'if [[ "$DAY_OF_MONTH" == "01" ]]' in script
    assert 'backups/${BACKUP_ENV}/monthly/${BACKUP_DATE_UTC}/db.dump.gpg.monthly' in script
    # Daily retention: deletes only YYYY-MM-DD prefixes (regex), skips `monthly`.
    assert '"$prefix" == "monthly"' in script
    assert '"$prefix" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$' in script
    assert 'aws "${AWS_CLI_ARGS[@]}" s3 rm' in script
    # Configurable retention window with safe default 30 days.
    assert 'BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"' in script


def test_verify_script_runs_3_sanity_checks_and_emits_audit_log() -> None:
    script = _verify_script()
    assert 'pg_restore --dbname="$VERIFY_URL"' in script
    assert "from app.tenants" in script
    assert "from app.conversations" in script
    assert "from app.messages" in script
    assert "'backup.verified'" in script
    assert 'insert into app.audit_logs' in script
    # The verify run is recorded with kind='cloud_verify'.
    assert "'cloud_verify'" in script


def test_verify_script_alerts_on_failure_with_null_tenant() -> None:
    script = _verify_script()
    assert "insert into app.operator_alerts" in script
    assert "'backup_failure'" in script
    # System-wide: tenant_id null.
    assert 'values (\n      null,\n      \'backup_failure\',' in script
    # SHA256 mismatch path is enforced.
    assert 'sha256_mismatch' in script
    # Empty dump / decrypt failures are wired.
    assert 'gpg_decrypt_failed' in script
    assert 'decrypted_dump_empty' in script


def test_docker_compose_wires_backup_worker_with_profile() -> None:
    compose = _compose()
    assert 'backup-worker:' in compose
    assert 'profiles: ["backups"]' in compose
    assert 'dockerfile: infra/backup-worker/Dockerfile' in compose
    assert './scripts:/app/scripts:ro' in compose
    assert './.secrets:/app/.secrets:ro' in compose
    assert 'BACKUP_S3_BUCKET:' in compose
    assert 'BACKUP_GPG_RECIPIENT:' in compose
    assert 'backup-logs:/var/log' in compose


def test_backup_worker_crontab_runs_daily_and_weekly_verify() -> None:
    cron_path = ROOT / 'infra' / 'backup-worker' / 'crontab'
    content = cron_path.read_text(encoding='utf-8')
    assert '0 3 * * *' in content
    assert 'backup-to-cloud.sh' in content
    assert '0 4 * * 0' in content
    assert 'verify-backup.sh' in content


def test_prometheus_alerts_for_backup_have_runbook() -> None:
    rules = _alerts()
    flat = [rule for group in rules['groups'] for rule in group['rules']]
    names = {r['alert']: r for r in flat}
    assert 'BackupCloudStale' in names
    assert 'BackupVerifyFailed' in names
    for alert in ('BackupCloudStale', 'BackupVerifyFailed'):
        annotations = names[alert]['annotations']
        assert annotations.get('runbook_url', '').endswith('backup-policy.md'), \
            f'{alert} missing runbook_url'


def test_backup_policy_doc_covers_rpo_restore_and_rotation() -> None:
    doc = (ROOT / 'docs' / 'backup-policy.md').read_text(encoding='utf-8')
    assert 'RPO' in doc
    assert '24 horas' in doc
    assert 'rotación' in doc.lower() or 'rotacion' in doc.lower()
    assert 'pg_restore' in doc
    assert '`scripts/backup-to-cloud.sh`' in doc
    assert '`scripts/verify-backup.sh`' in doc
    assert 'BackupCloudStale' in doc and 'BackupVerifyFailed' in doc


def test_backup_scripts_have_valid_bash_syntax() -> None:
    bash = shutil.which('bash')
    assert bash is not None, 'bash binary not available on PATH'
    for name in ('backup-to-cloud.sh', 'verify-backup.sh'):
        path = ROOT / 'scripts' / name
        result = subprocess.run([bash, '-n', str(path)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, f'{name} falló bash -n: {result.stderr}'
