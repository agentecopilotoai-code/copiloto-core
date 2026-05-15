# Runbook — Configuración del modelo de firma de backups (SEC-009)

**Owner operacional:** SRE de turno.
**Ticket:** SEC-009 — Backup verification trust model.
**Cuándo aplicar:** una sola vez al provisionar el cluster (o ante rotación de claves). Documentar el resultado en `docs/security-findings-triage-2026-05-15.md` y en el ticket de rotación.

---

## Motivación

Antes de SEC-009 el verifier semanal:

1. Confiaba en `Metadata.sha256` del propio objeto S3 (cualquiera con permisos de escritura sobre el bucket podía inyectar un objeto malicioso con el sha256 que quisiera).
2. Descifraba con GPG sin verificar autenticidad (la clave privada de descifrado autentica al destinatario, no al emisor).
3. Restauraba sobre el **mismo cluster Postgres productivo** con el rol `postgres` superuser — un dump adversario podía ejecutar triggers / `COPY ... FROM PROGRAM` con efectos persistentes.

Tras SEC-009 hay tres capas, todas requeridas:

- **Capa 1 (firma detached GPG):** el productor firma `db.dump.gpg` con `gpg --detach-sign` y sube `db.dump.gpg.sig` al mismo prefijo. El verifier importa la pubkey del signer en build-time del container (out-of-band, NO desde el bucket) y corre `gpg --verify` antes de cualquier `--decrypt`. Si falta la firma o no valida, falla cerrado.
- **Capa 2 (Postgres efímero isolated):** el verifier levanta un `postgres:16-alpine` desechable en una red bridge `--internal` (`backup-verify-net`). El restore aterriza ahí, no en el cluster productivo. Tear-down post-verify.
- **Capa 3 (rol non-superuser):** el restore usa `backup_verifier` (rol creado al arranque del Postgres efímero, sin SUPERUSER, REPLICATION, BYPASSRLS, CREATEROLE ni CREATEDB).

---

## Modelo de claves

Hay **dos pares GPG distintos** en la operación de backups:

| Par              | Propósito           | Privada vive en | Pública vive en                  |
| ---------------- | ------------------- | --------------- | -------------------------------- |
| **Recipient**    | Cifrar el dump      | Verifier        | Producer (recipient para `--encrypt`) |
| **Signer**       | Firmar el dump cifrado | Producer    | Verifier (out-of-band)            |

No reutilizar el mismo par para ambas funciones. El producer NUNCA debe tener la privada del recipient (de lo contrario podría descifrar sus propios backups, no es necesario). El verifier NUNCA debe tener la privada del signer (de lo contrario podría re-firmar dumps, anulando la autenticidad).

---

## Procedimiento de generación (one-time)

### 1. Crear el par del signer

Ejecutar en un host **separado** del verifier (laptop offline, HSM, o vault administrado):

```bash
gpg --batch --gen-key <<EOF
%no-protection
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: CopilotoIA Backup Signer
Name-Email: backup-signer@copilotoia.internal
Expire-Date: 2y
%commit
EOF
```

Obtener el fingerprint:

```bash
gpg --list-secret-keys --keyid-format=long backup-signer@copilotoia.internal
# Anotar el fingerprint completo (40 hex chars) → BACKUP_SIGNER_FPR.
```

Exportar las claves:

```bash
gpg --armor --export-secret-keys backup-signer@copilotoia.internal > backup_signer_privkey.asc
gpg --armor --export             backup-signer@copilotoia.internal > backup_signer_pubkey.asc
```

### 2. Distribuir las claves

**Privada (signer) → solo producer host:**

```bash
# En el host donde corre scripts/backup-to-cloud.sh:
mkdir -p .secrets && chmod 700 .secrets
mv /ruta/de/transporte/backup_signer_privkey.asc .secrets/
chmod 600 .secrets/backup_signer_privkey.asc
```

**Pública (signer) → solo verifier container:**

```bash
# En el host donde corre el verifier (backup-worker):
mkdir -p .secrets && chmod 700 .secrets
mv /ruta/de/transporte/backup_signer_pubkey.asc .secrets/
chmod 600 .secrets/backup_signer_pubkey.asc
```

> **Importante:** la pubkey del signer **no debe** vivir en el bucket S3. Si la subes ahí, anulas SEC-009 — un atacante con write al bucket podría reemplazar tanto el dump como la pubkey con su propia firma. El runbook fuerza el path `/app/.secrets/backup_signer_pubkey.asc` (montado read-only desde fuera del bucket).

### 3. Configurar variables de entorno

En `.env` (o el secret manager equivalente):

```bash
# Producer
BACKUP_SIGNER_FPR=<fingerprint del paso 1>
BACKUP_SIGNER_PRIVKEY_PATH=/app/.secrets/backup_signer_privkey.asc

# Verifier
BACKUP_SIGNER_PUBKEY_PATH=/app/.secrets/backup_signer_pubkey.asc
```

### 4. Smoke test (no destructivo)

```bash
# Producer (simulacro):
docker compose --profile backups run --rm backup-worker /app/scripts/backup-to-cloud.sh

# Verifier (al día siguiente, o forzando TARGET_DATE):
docker compose --profile backups run --rm backup-worker \
  /app/scripts/verify-backup.sh --date YYYY-MM-DD
```

El output debe terminar en `Backup verify OK [ephemeral_isolated]: tenants=N ...`. Si dice `[degraded_list_only]`, el host no tiene acceso al docker socket — ver sección "Modo degraded".

---

## Modo degraded (SEC-009.1-FU)

Si el verifier corre en un entorno sin acceso al docker socket (host bare-metal con políticas restrictivas, runner gestionado, etc.), setear:

```bash
BACKUP_VERIFY_SKIP_EPHEMERAL=1
```

En este modo el verifier corre `pg_restore --list` sobre el dump descifrado para validar parseability + cuenta tablas del schema `app.`, pero **no ejecuta** un restore real. **Esto NO es un sustituto válido a Layer 2.** El ticket de follow-up es `SEC-009.1-FU` — hardening adicional (p.ej. levantar el Postgres efímero vía `systemd-nspawn` o `podman` sin necesidad del docker socket).

El audit log registra `restore_mode='degraded_list_only'` para que el operador detecte el degraded mode en `app.backup_runs.metadata`.

---

## Rotación

Cada **2 años** o ante sospecha de compromiso:

1. Generar nuevo par (sección "Procedimiento de generación", paso 1).
2. Distribuir **ambas** claves nuevas (paso 2).
3. Actualizar `BACKUP_SIGNER_FPR` en `.env`.
4. Re-deploy del producer + verifier.
5. Backups firmados con la clave vieja siguen verificables siempre que la pubkey vieja permanezca importada en el verifier (recomendado: mantener ambas durante 30 días para no perder verificabilidad de los daily snapshots en retención).
6. Borrar la privada vieja del producer (`shred -u .secrets/backup_signer_privkey.asc.old`).

---

## Verificación manual de un backup individual

Útil ante incidente o auditoría externa:

```bash
aws s3 cp s3://$BACKUP_S3_BUCKET/backups/$BACKUP_ENV/YYYY-MM-DD/db.dump.gpg /tmp/d.gpg
aws s3 cp s3://$BACKUP_S3_BUCKET/backups/$BACKUP_ENV/YYYY-MM-DD/db.dump.gpg.sig /tmp/d.gpg.sig

gpg --import .secrets/backup_signer_pubkey.asc
gpg --verify /tmp/d.gpg.sig /tmp/d.gpg
# Debe imprimir "Good signature from CopilotoIA Backup Signer".
```

---

## Failure modes esperados

| Causa raíz                                    | Mensaje del verifier                              |
| --------------------------------------------- | ------------------------------------------------- |
| Falta `.sig` en S3 (producer no firmó)        | `missing_detached_signature:sec_009_fail_closed` |
| Firma no valida (objeto mutado o clave equivocada) | `gpg_verify_failed:...` o `gpg_verify_no_goodsig` |
| Docker socket no disponible / sin permisos    | Cae a modo degraded; revisar `restore_mode` en metadata |
| Postgres efímero no inicia                    | `ephemeral_pg_start_failed:...`                  |
| Postgres efímero no responde (timeout 30s)    | `ephemeral_pg_not_ready`                         |
| Rol `backup_verifier` no se pudo crear        | `ephemeral_role_provision_failed:...`            |
| `pg_restore` falla parseando el dump          | `pg_restore_failed:...`                          |

Todos los failure modes emiten un `operator_alerts(kind='backup_failure')` con `tenant_id=null`, igual que el flujo anterior. El alerting de Prometheus en `infra/observability/alerts.yaml` (`BackupVerifyFailed`) los recoge sin cambios.

---

## Referencias

- `scripts/backup-to-cloud.sh` — producer (líneas marcadas `SEC-009`).
- `scripts/verify-backup.sh` — consumer.
- `infra/backup-worker/Dockerfile` — install de `docker.io` + `openssl`.
- `infra/backup-worker/entrypoint.sh` — import idempotente de las claves al boot.
- `docker-compose.yml` (servicio `backup-worker`) — env vars y mount del docker socket.
- `docs/security-findings-triage-2026-05-15.md` — row `0ebe3783` actualizado a RESOLVED-SEC-009-PR.
