# Política de backups — CopilotoIA (TASK-0064)

Este documento describe el procedimiento operativo de backup cloud, retención, verificación periódica y restauración. Sustituye el enfoque exclusivamente local de TASK-0029 (drill validado, pero limitado a la pérdida de datos dentro del host).

## Objetivos

- **RPO objetivo:** ≤ 24 horas (un dump diario cifrado).
- **RTO objetivo:** ≤ 2 horas (restore desde el último dump verificado).
- **Confidencialidad en reposo:** cada dump se cifra con GPG (curva 25519 / RSA 4096) antes de subirse al bucket.
- **Confidencialidad en tránsito:** TLS contra el endpoint S3 (`https://`).
- **Verificación:** restore real y `select count(*)` semanal sobre una base efímera.
- **Aislamiento del host:** los backups viven en un bucket administrado fuera del host de la app.

## Componentes

| Pieza | Ubicación |
|---|---|
| Script de dump + upload | `scripts/backup-to-cloud.sh` |
| Script de verificación | `scripts/verify-backup.sh` |
| Worker con cron | `infra/backup-worker/` (servicio `backup-worker` en docker-compose, perfil `backups`) |
| Tabla operativa | `app.backup_runs` |
| Eventos de auditoría | `app.audit_logs(action='backup.verified' | 'backup.verify_failed')` |
| Alertas operativas | `app.operator_alerts(kind='backup_failure')` (tenant NULL = system-wide) |
| Reglas Prometheus | `BackupCloudStale`, `BackupVerifyFailed` en `infra/observability/alerts.yaml` |
| Clave pública GPG | `.secrets/backup_gpg_pubkey.asc` |
| Clave privada GPG (sólo nodo de verificación) | `.secrets/backup_gpg_privkey.asc` |

## Variables de entorno

```
BACKUP_S3_BUCKET=copilotoia-backups-prod
BACKUP_ENV=prod
BACKUP_S3_ENDPOINT=https://s3.us-east-1.amazonaws.com   # opcional; vacío = SDK default
BACKUP_GPG_RECIPIENT=ops-backups@copilotoia.io           # fingerprint o email
BACKUP_GPG_PUBKEY_PATH=/app/.secrets/backup_gpg_pubkey.asc
BACKUP_RETENTION_DAYS=30
DATABASE_ADMIN_URL=postgres://copiloto_admin@postgres:5432/copilotoia
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

Para entornos locales con MinIO, el `BACKUP_S3_ENDPOINT` apunta a `http://minio:9000`.

## Calendario

| Job | Schedule (UTC) | Script |
|---|---|---|
| Dump diario | `0 3 * * *` | `backup-to-cloud.sh` |
| Verificación semanal | `0 4 * * 0` (domingo) | `verify-backup.sh` |

Cada ejecución deja una fila en `app.backup_runs` con `kind in ('cloud_dump','cloud_verify')`, `status`, `sha256`, `size_bytes`, `duration_seconds` y `evidence_path` (URI del objeto en S3).

## Política de retención

- **Diarios:** 30 días bajo `s3://<bucket>/backups/<env>/<YYYY-MM-DD>/db.dump.gpg`.
- **Mensuales:** el dump del día 01 de cada mes se copia adicionalmente a `s3://<bucket>/backups/<env>/monthly/<YYYY-MM-DD>/db.dump.gpg.monthly` y queda preservado 12 meses (la purga del script no toca el prefijo `monthly/`).
- **Política inalterable por accidente:** el script sólo invoca `aws s3 rm` sobre prefijos cuya carpeta coincide con `YYYY-MM-DD`; cualquier otra entrada (incluyendo `monthly/`) se ignora.

## Procedimiento de rotación de la clave GPG

1. Genera el nuevo par: `gpg --quick-gen-key 'ops-backups-2027@copilotoia.io' ed25519 cert,sign 1y`.
2. Exporta la pública: `gpg --export --armor ops-backups-2027 > .secrets/backup_gpg_pubkey.asc` (sustituye el archivo existente).
3. Mantén la clave anterior en `secrets/archive/backup_gpg_pubkey-YYYY.asc` para poder descifrar dumps antiguos.
4. Actualiza la variable `BACKUP_GPG_RECIPIENT` con el nuevo email/fingerprint.
5. Despliega el `backup-worker`. El primer dump posterior queda cifrado con la nueva clave.
6. Importa la nueva clave privada **únicamente en el nodo de verificación**.
7. Documenta la rotación en `audit_logs(action='backup.gpg_rotated', metadata={old, new})` desde el panel admin (o vía SQL controlado).

## Procedimiento de restore (DR)

1. Identifica el run a restaurar:
   ```sql
   select id, started_at, evidence_path, sha256
     from app.backup_runs
    where kind='cloud_dump' and status='ok'
    order by started_at desc
    limit 5;
   ```
2. Descarga el objeto:
   ```bash
   aws s3 cp s3://<bucket>/backups/<env>/<YYYY-MM-DD>/db.dump.gpg ./db.dump.gpg
   sha256sum ./db.dump.gpg   # debe coincidir con backup_runs.sha256
   ```
3. Descifra con la clave privada (sólo accesible al equipo DR):
   ```bash
   gpg --batch --output ./db.dump --decrypt ./db.dump.gpg
   ```
4. Restaura sobre la DB destino (debe estar limpia):
   ```bash
   pg_restore --dbname=postgres://copiloto_admin@<host>/copilotoia \
              --clean --if-exists --no-owner --no-privileges \
              --exit-on-error ./db.dump
   ```
5. Compara los conteos contra los registrados en el run verificado:
   ```bash
   psql "$DATABASE_ADMIN_URL" -c "
     select 'tenants', count(*) from app.tenants
     union all select 'conversations', count(*) from app.conversations
     union all select 'messages', count(*) from app.messages;
   "
   ```
6. Documenta el restore con `audit_logs(action='backup.restored', metadata={run_id, restored_at})`.

## Triage cuando una alerta dispara

| Alerta | Síntoma | Mitigación inmediata |
|---|---|---|
| `BackupCloudStale` | sin `cloud_dump status=ok` en >30h | inspecciona logs del worker, verifica credenciales S3, reintenta `scripts/backup-to-cloud.sh` manualmente |
| `BackupVerifyFailed` | último `cloud_verify` falló | revisa la causa en `app.backup_runs.error`, confirma que la clave privada esté disponible en el verificador, revierte un upload corrupto |

## Notas de diseño

- El bucket recibe objetos cifrados; ni siquiera el operador de cloud ve PII.
- `app.backup_runs` no tiene `tenant_id` (los backups snapshotean el cluster completo) y por eso no entra al loop RLS estándar; el acceso queda controlado por el rol que tiene permisos sobre la tabla (admin/ops).
- `operator_alerts(kind='backup_failure', tenant_id=null)` es system-wide. La restricción `chk_operator_alerts_system_alerts_have_no_tenant` exige que sólo este `kind` use `tenant_id IS NULL`.
- El script de retención sólo opera sobre prefijos `YYYY-MM-DD` y no toca `monthly/`. Cualquier otro prefijo es ignorado para evitar borrados accidentales en buckets compartidos.
