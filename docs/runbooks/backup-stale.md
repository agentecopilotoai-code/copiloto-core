# Runbook — Backup stale

**Alerta:** `BackupStale` (severity: ticket)
**Trigger:** `cpi_backup_last_success_age_seconds{kind="cloud_dump"} > 86400` (24h)
**Categoría:** Infraestructura / Backup
**Escalación:** Si llega a 30h dispara `BackupCloudStale` (severity: page).

---

## Síntoma

- El último `cloud_dump` exitoso tiene > 24h.
- RPO formal es 30h — todavía en banda pero acercándose al límite.

## Diagnóstico

1. **Logs del backup-worker:**

   ```bash
   docker logs backup-worker --tail=200
   # o
   kubectl logs -l app=backup-worker --tail=200
   ```

2. **Estado en DB:**

   ```sql
   select kind, status, started_at, finished_at, error
   from app.backup_runs
   where kind in ('cloud_dump','cloud_verify')
   order by started_at desc
   limit 10;
   ```

3. **Credenciales S3 + GPG en el pod:**

   ```bash
   kubectl exec deployment/backup-worker -- env | grep -E "BACKUP_|AWS_"
   # Verificar:
   #   - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY no vacíos
   #   - BACKUP_S3_BUCKET seteado
   #   - BACKUP_GPG_PUBKEY_PATH apunta a un archivo existente
   ```

4. **¿El scheduler cron está corriendo?**

   ```bash
   kubectl get deployment backup-worker -o jsonpath='{.status.availableReplicas}'
   # Debe ser >= 1
   ```

## Mitigación

### Caso A — Worker caído

```bash
kubectl get pods -l app=backup-worker
# Si está en CrashLoopBackOff:
kubectl logs <pod> --previous --tail=50
# Si está en Pending: revisar resources / node selector.
kubectl rollout restart deployment/backup-worker
```

### Caso B — S3 credentials inválidas

Validar manualmente:

```bash
aws s3 ls s3://$BACKUP_S3_BUCKET/ --profile=copilotoia-backup
```

Si falla 403/AccessDenied → rotar las creds con el infra team y
actualizar el secret.

### Caso C — GPG key no encontrada

```bash
kubectl exec deployment/backup-worker -- ls -la $BACKUP_GPG_PUBKEY_PATH
# Si "No such file": montar el volume con la key.
```

### Caso D — Backup ejecutándose pero fallando

Mirar el `error` column del paso 2. Casos típicos:

- `pg_dump: error: connection to server failed` — postgres host
  no resoluble desde el worker. Revisar networking.
- `Connection reset by peer` durante upload S3 — retry suele
  funcionar; si persiste, revisar región/endpoint S3.
- `gpg: encryption failed: No public key` — el `BACKUP_GPG_RECIPIENT`
  no matchea ninguna key importada.

### Forzar un backup manual

```bash
kubectl exec deployment/backup-worker -- bash scripts/run-cloud-backup.sh
```

Si termina OK, el gauge `cpi_backup_last_success_age_seconds` baja
a ~0 en el próximo scrape (≤30s) y la alerta se resuelve.

## Verificación

- Insert nueva fila en `app.backup_runs` con `status='ok'`.
- `cpi_backup_last_success_age_seconds{kind="cloud_dump"} < 3600`.
- Próximo run programado (cron del worker) ejecutará a tiempo.

## Última revisión

2026-05-27 — TASK-PROD post audit#4.
