#!/usr/bin/env bash
# TASK-0064 / SEC-009 — Verificación periódica de backups en cloud.
#
# SEC-009 hardening (2026-05-15): el verifier ahora corre en un trust model
# end-to-end más estricto:
#   * Capa 1 — `gpg --verify` con detached signature contra una pubkey importada
#     out-of-band en el container (NO descargada del bucket). Falla cerrado si
#     `db.dump.gpg.sig` no existe o la firma no coincide. La hash en
#     `Metadata.sha256` deja de ser autoritativa (sigue auditada para
#     correlación pero ya no decide).
#   * Capa 2 — la restauración ocurre en un Postgres efímero (`postgres:16`)
#     levantado por este script en su propia red bridge isolated (`docker
#     network create --internal`). NUNCA toca el cluster productivo.
#   * Capa 3 — el rol que ejecuta el restore es `backup_verifier`
#     (non-superuser); el `postgres` superuser solo se usa al inicio para
#     provisionar el rol y otorgar privilegios mínimos sobre la DB efímera.
#
# Resultado:
#   * éxito → `audit_logs(action='backup.verified')`.
#   * fallo → `operator_alerts(kind='backup_failure')` + audit log con la causa.
#
# Diseñado para correr semanalmente (cron `0 4 * * 0` en docker-compose).
#
# Variables requeridas:
#   BACKUP_S3_BUCKET            bucket origen.
#   BACKUP_ENV                  prefijo de ambiente.
#   DATABASE_ADMIN_URL          conexión administrativa para escribir el run en
#                               el CLUSTER PRODUCTIVO (sólo writes a
#                               app.backup_runs / audit_logs / operator_alerts —
#                               no es target de restore).
#   BACKUP_SIGNER_PUBKEY_PATH   ruta al .asc PÚBLICO del signer (importado en
#                               build-time del container). El verifier abortará
#                               si no encuentra esta clave.
#
# Variables opcionales:
#   BACKUP_S3_ENDPOINT                endpoint custom (MinIO local).
#   BACKUP_GPG_PRIVATE_KEY_PATH       ruta al .asc privado (sólo para CI/host).
#   BACKUP_VERIFY_PG_IMAGE            imagen del Postgres efímero (default
#                                     `postgres:16-alpine`).
#   BACKUP_VERIFY_PG_PORT             puerto local del Postgres efímero
#                                     (default 55432).
#   BACKUP_VERIFY_NETWORK             nombre de la red bridge isolated (default
#                                     `backup-verify-net`).
#   BACKUP_VERIFY_SKIP_EPHEMERAL=1    fallback de stop-gap: si el daemon Docker
#                                     no está disponible (p.ej. host bare-metal
#                                     sin acceso al socket), corre el restore
#                                     en `--schema-only` envuelto en una
#                                     transacción que se ROLLBACK-ea contra
#                                     `POSTGRES_HOST` (NO el productivo). Esto
#                                     es un degraded mode documentado: ver
#                                     SEC-009.1-FU.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'MSG'
Uso: ./scripts/verify-backup.sh [--date YYYY-MM-DD]

Descarga el último backup (o el del día indicado), restaura sobre
copilotoia_verify y reporta el resultado a audit_logs / operator_alerts.
MSG
}

TARGET_DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      TARGET_DATE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opción no reconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "Error: variable $name es requerida." >&2
    exit 2
  fi
}

require_var BACKUP_S3_BUCKET
require_var BACKUP_ENV
require_var DATABASE_ADMIN_URL

# SEC-009 — la pubkey del signer es OBLIGATORIA y vive en el container, no en
# el bucket. Sin esta clave el verifier no puede `gpg --verify` y debe abortar.
BACKUP_SIGNER_PUBKEY_PATH="${BACKUP_SIGNER_PUBKEY_PATH:-/app/.secrets/backup_signer_pubkey.asc}"
if [[ ! -f "$BACKUP_SIGNER_PUBKEY_PATH" ]]; then
  echo "Error: SEC-009 — pubkey del signer no encontrada en $BACKUP_SIGNER_PUBKEY_PATH." >&2
  echo "  Ver docs/runbooks/backup-signature-setup.md." >&2
  exit 2
fi

for tool in aws gpg pg_restore psql sha256sum; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: falta dependencia '$tool' en el PATH." >&2
    exit 2
  fi
done

# SEC-009 — parámetros del Postgres efímero. La red `--internal` impide que el
# container desechable salga al exterior o alcance el cluster productivo, aún
# si el dump contiene triggers / `COPY ... FROM PROGRAM` adversarios.
#
# Default image: `pgvector/pgvector:pg16` — el schema productivo usa pgvector
# para `app.knowledge_chunks.embedding vector(1536)`, así que cualquier dump
# real lleva entries de la extensión `vector` que `pg_restore` ejecuta. Con la
# imagen plain `postgres:16-alpine` el restore fallaba al toparse con esos
# objects (codex P1 SEC-009.1). La imagen oficial pgvector es un drop-in de
# Postgres 16 con la extensión pre-instalada.
BACKUP_VERIFY_PG_IMAGE="${BACKUP_VERIFY_PG_IMAGE:-pgvector/pgvector:pg16}"
BACKUP_VERIFY_PG_PORT="${BACKUP_VERIFY_PG_PORT:-55432}"
BACKUP_VERIFY_NETWORK="${BACKUP_VERIFY_NETWORK:-backup-verify-net}"
BACKUP_VERIFY_PG_CONTAINER="copilotoia-verify-pg-$$"

# SEC-009 networking fix (codex P1) — cuando el verifier corre dentro de un
# container (backup-worker en docker-compose), el `127.0.0.1` del propio
# container NO es el host del Docker daemon. `docker run -p 127.0.0.1:...`
# publica el puerto en el HOST del daemon, así que `psql -h 127.0.0.1`
# desde dentro del worker apunta a su propio loopback (vacío) y se cuelga
# con `ephemeral_pg_not_ready` aunque el ephemeral haya arrancado bien.
#
# Detectamos el modo de ejecución con `/.dockerenv` y elegimos transporte:
#
#   * EN_DOCKER=1 → resolvemos vía DNS de Docker: el ephemeral se une a
#     `BACKUP_VERIFY_NETWORK`, el worker se conecta TEMPORALMENTE a esa
#     red, y `psql -h <ephemeral_container_name> -p 5432`. NO publicamos
#     puerto al host (sin `-p`). Cleanup desconecta el worker antes de
#     borrar la red.
#   * EN_DOCKER=0 → host bare-metal / CI runner: mantenemos el comporta-
#     miento original (`-p 127.0.0.1:${PORT}:5432` + `psql -h 127.0.0.1`).
EN_DOCKER=0
WORKER_CONTAINER_ID=""
# SEC-009.1-FU: además de `/.dockerenv` (Docker), reconocemos
# `/run/.containerenv` (Podman / runc) para que el worker se
# autodetecte correctamente cuando el verifier corre bajo un runtime
# rootless. Sin esto, `EN_DOCKER=0` activaba la lógica bare-metal
# (`-p 127.0.0.1:PORT`) que en un container apunta al loopback equivocado.
if [[ -f /.dockerenv ]] || [[ -f /run/.containerenv ]]; then
  EN_DOCKER=1
  # `hostname` dentro de un container devuelve el container ID corto;
  # tanto `docker inspect` como `podman inspect` lo aceptan.
  WORKER_CONTAINER_ID="$(hostname)"
fi

# SEC-009.1-FU: selección de runtime. Prefiere `docker` (compat con el
# escenario actual del compose), cae a `podman` cuando docker no está
# disponible o su daemon no responde (hosts rootless / managed runners
# que no exponen el socket). Si ni docker ni podman funcionan, queda
# vacío y el script cae al modo degradado (`pg_restore --list`).
CONTAINER_CMD=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  CONTAINER_CMD="docker"
elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
  CONTAINER_CMD="podman"
fi
BACKUP_VERIFY_SUPERUSER_PASSWORD="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | base64)"
BACKUP_VERIFY_RESTORE_PASSWORD="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | base64)"
VERIFY_DB="copilotoia_verify"
VERIFY_RESTORE_ROLE="backup_verifier"

AWS_CLI_ARGS=()
if [[ -n "${BACKUP_S3_ENDPOINT:-}" ]]; then
  AWS_CLI_ARGS+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
fi

if [[ -z "$TARGET_DATE" ]]; then
  TARGET_DATE="$(date -u +%Y-%m-%d)"
fi
S3_KEY="backups/${BACKUP_ENV}/${TARGET_DATE}/db.dump.gpg"
S3_URI="s3://${BACKUP_S3_BUCKET}/${S3_KEY}"
# SEC-009 — la firma detached sibling es REQUERIDA. Falla cerrado si falta.
S3_KEY_SIG="${S3_KEY}.sig"
S3_URI_SIG="s3://${BACKUP_S3_BUCKET}/${S3_KEY_SIG}"

WORK_DIR="$(mktemp -d -t copilotoia-verify-XXXXXX)"

cleanup_ephemeral_pg() {
  # SEC-009 — tear-down del Postgres efímero y su red. Idempotente:
  # tolera el caso degraded donde no había runtime de container, y
  # funciona tanto con `docker` como con `podman` (SEC-009.1-FU).
  if [[ -n "$CONTAINER_CMD" ]]; then
    "$CONTAINER_CMD" rm -f "$BACKUP_VERIFY_PG_CONTAINER" >/dev/null 2>&1 || true
    # codex P1: si conectamos el worker a la red verify (cuando EN_DOCKER=1),
    # hay que desconectarlo ANTES de borrar la red — sino `network rm` falla
    # con `has active endpoints`. Aplica igual para podman.
    if [[ "$EN_DOCKER" == "1" && -n "$WORKER_CONTAINER_ID" ]]; then
      "$CONTAINER_CMD" network disconnect "$BACKUP_VERIFY_NETWORK" "$WORKER_CONTAINER_ID" \
        >/dev/null 2>&1 || true
    fi
    "$CONTAINER_CMD" network rm "$BACKUP_VERIFY_NETWORK" >/dev/null 2>&1 || true
  fi
}

trap 'rm -rf "$WORK_DIR"; cleanup_ephemeral_pg' EXIT

ENC_PATH="$WORK_DIR/db.dump.gpg"
SIG_PATH="$WORK_DIR/db.dump.gpg.sig"
DUMP_PATH="$WORK_DIR/db.dump"

RUN_ID="$(psql "$DATABASE_ADMIN_URL" -Atc "select gen_random_uuid()")"

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -v evidence="$S3_URI" -Atc "
  insert into app.backup_runs (id, kind, status, evidence_path, metadata)
  values (
    :'run_id'::uuid,
    'cloud_verify',
    'running',
    :'evidence',
    jsonb_build_object('target_date','${TARGET_DATE}','env','${BACKUP_ENV}')
  )
" >/dev/null

report_failure() {
  local err_msg="$1"
  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" -Atc "
    update app.backup_runs
       set status='failed', finished_at=now(), error=:'err_msg'
     where id=:'run_id'::uuid
  " >/dev/null || true

  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" \
       -v evidence="$S3_URI" -v env="$BACKUP_ENV" -Atc "
    insert into app.operator_alerts (tenant_id, kind, payload)
    values (
      null,
      'backup_failure',
      jsonb_build_object(
        'run_id', :'run_id',
        'env', :'env',
        'evidence_path', :'evidence',
        'phase', 'verify',
        'error', :'err_msg'
      )
    )
  " >/dev/null || true

  psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 \
       -v run_id="$RUN_ID" -v err_msg="$err_msg" -Atc "
    insert into app.audit_logs (tenant_id, actor_type, action, entity_type, entity_id, metadata)
    values (
      null,
      'service',
      'backup.verify_failed',
      'backup_runs',
      :'run_id',
      jsonb_build_object('error', :'err_msg', 'evidence_path', '${S3_URI}')
    )
  " >/dev/null || true

  echo "Backup verify FAILED: $err_msg" >&2
  exit 1
}

echo "==> Descargando $S3_URI"
if ! aws "${AWS_CLI_ARGS[@]}" s3 cp "$S3_URI" "$ENC_PATH" --only-show-errors; then
  report_failure "s3_download_failed"
fi

if [[ ! -s "$ENC_PATH" ]]; then
  report_failure "downloaded_artifact_empty"
fi

# SEC-009 — descarga la firma detached. Si no existe, fail-closed: backups
# anteriores a SEC-009 sin firma quedan deliberadamente NO verificables hasta
# que el producer empiece a firmar. Esto es el comportamiento intencional —
# preferimos ruido operacional sobre confiar en un objeto no autenticado.
echo "==> Descargando firma detached $S3_URI_SIG"
if ! aws "${AWS_CLI_ARGS[@]}" s3 cp "$S3_URI_SIG" "$SIG_PATH" --only-show-errors; then
  report_failure "missing_detached_signature:sec_009_fail_closed"
fi
if [[ ! -s "$SIG_PATH" ]]; then
  report_failure "signature_artifact_empty"
fi

# SEC-009 — el sha256 se sigue calculando para correlación con audit_logs, pero
# YA NO se compara contra `Metadata.sha256` (controlado por quien escribe el
# bucket). La autoridad es ahora la firma GPG.
LOCAL_SHA="$(sha256sum "$ENC_PATH" | awk '{print $1}')"

# SEC-009 — verifica la firma ANTES de descifrar. El verifier importa la
# pubkey del signer en build-time del container (NO la baja del bucket). Si la
# firma no valida, abortamos sin descifrar — esto cierra el path donde un
# atacante con write a S3 inyecta un blob malicioso esperando que el decrypt
# y el restore subsiguientes lo ejecuten.
echo "==> Verificando firma detached (SEC-009)"
# Import idempotente de la pubkey del signer (no-op si ya está en keyring).
gpg --batch --quiet --import "$BACKUP_SIGNER_PUBKEY_PATH" >/dev/null 2>&1 || true
if ! gpg --batch --status-fd 1 --verify "$SIG_PATH" "$ENC_PATH" >"$WORK_DIR/verify.out" 2>"$WORK_DIR/verify.err"; then
  report_failure "gpg_verify_failed:$(tail -c 200 "$WORK_DIR/verify.err" | tr '\n' ' ')"
fi
# Defense in depth: GOODSIG en stdout machine-readable.
if ! grep -q '^\[GNUPG:\] GOODSIG ' "$WORK_DIR/verify.out"; then
  report_failure "gpg_verify_no_goodsig"
fi
# BUG-079: GOODSIG sólo dice "alguna pubkey del keyring firmó esto" —
# el entrypoint también importa la pubkey de encryption, así que un
# atacante con acceso a esa key podría firmar un blob malicioso y pasaría
# el GOODSIG check. Exigimos que la firma sea del FINGERPRINT canónico
# `BACKUP_SIGNER_FPR`. El payload de GOODSIG es: `GOODSIG <fingerprint>
# <uid>`. Lo extraemos y comparamos.
#
# BUG-175 (codex P1 sobre BUG-079): el `if [[ -n "${BACKUP_SIGNER_FPR}" ]]`
# original silenciosamente skippeaba la validación cuando la env var
# estaba vacía/unset → caía al accept-any-GOODSIG behavior que BUG-079
# justamente quería cerrar. La compose default es empty y el entrypoint
# solo exporta vars no-vacías, así que la regresión es real. Ahora la
# var es REQUERIDA: si está vacía, fail-closed con setup error claro.
if [[ -z "${BACKUP_SIGNER_FPR:-}" ]]; then
  report_failure "backup_signer_fpr_unset:set BACKUP_SIGNER_FPR to the canonical signer fingerprint (40 hex chars) in compose/entrypoint"
fi
GOODSIG_LINE="$(grep -m 1 '^\[GNUPG:\] GOODSIG ' "$WORK_DIR/verify.out")"
GOODSIG_FPR="$(awk '{print $3}' <<<"$GOODSIG_LINE")"
# GPG entrega el "long key ID" (16 hex) o el fingerprint completo (40 hex)
# dependiendo de la versión. Aceptamos suffix-match contra el FPR esperado.
if [[ -z "$GOODSIG_FPR" ]] || [[ ! "${BACKUP_SIGNER_FPR^^}" =~ "${GOODSIG_FPR^^}"$ ]]; then
  report_failure "gpg_verify_wrong_signer:expected=${BACKUP_SIGNER_FPR},actual=${GOODSIG_FPR}"
fi

echo "==> Descifrando con GPG (post-verify)"
if ! gpg --batch --yes --quiet --output "$DUMP_PATH" --decrypt "$ENC_PATH"; then
  report_failure "gpg_decrypt_failed"
fi

if [[ ! -s "$DUMP_PATH" ]]; then
  report_failure "decrypted_dump_empty"
fi

# SEC-009 — Layer 2: arranque del Postgres efímero ISOLATED. La red bridge se
# crea con `--internal` para que el container no tenga acceso al cluster
# productivo aún si el dump contiene payloads adversarios (triggers que
# intenten `COPY ... FROM PROGRAM`, dblink, etc.).
EPHEMERAL_PG_OK=0
if [[ "${BACKUP_VERIFY_SKIP_EPHEMERAL:-0}" != "1" ]] && [[ -n "$CONTAINER_CMD" ]]; then
  echo "==> Creando red isolated ${BACKUP_VERIFY_NETWORK} (runtime=${CONTAINER_CMD})"
  # `--internal` impide tráfico fuera de la red bridge. Funciona igual
  # con docker y podman (ambos soportan `--driver bridge --internal`).
  "$CONTAINER_CMD" network create --driver bridge --internal "$BACKUP_VERIFY_NETWORK" >/dev/null 2>&1 || \
    "$CONTAINER_CMD" network inspect "$BACKUP_VERIFY_NETWORK" >/dev/null 2>&1 || \
    report_failure "ephemeral_network_create_failed"

  # codex P1 fix — `run -p 127.0.0.1:${PORT}:5432` publica al HOST del
  # runtime, no al worker. Solo lo usamos cuando el verifier corre en
  # bare-metal/CI (sin /.dockerenv y sin /run/.containerenv). Dentro de
  # un container, omitimos `-p` y nos conectamos al ephemeral por DNS
  # del runtime (`<container_name>:5432`).
  PORT_PUBLISH_ARGS=()
  if [[ "$EN_DOCKER" != "1" ]]; then
    PORT_PUBLISH_ARGS=(-p "127.0.0.1:${BACKUP_VERIFY_PG_PORT}:5432")
  fi

  echo "==> Arrancando Postgres efímero ${BACKUP_VERIFY_PG_IMAGE}"
  if ! "$CONTAINER_CMD" run -d --rm \
        --name "$BACKUP_VERIFY_PG_CONTAINER" \
        --network "$BACKUP_VERIFY_NETWORK" \
        "${PORT_PUBLISH_ARGS[@]}" \
        -e POSTGRES_PASSWORD="$BACKUP_VERIFY_SUPERUSER_PASSWORD" \
        -e POSTGRES_DB="$VERIFY_DB" \
        "$BACKUP_VERIFY_PG_IMAGE" >/dev/null 2>"$WORK_DIR/runtime.err"; then
    report_failure "ephemeral_pg_start_failed:$(tail -c 200 "$WORK_DIR/runtime.err" | tr '\n' ' ')"
  fi

  # codex P1 fix — cuando estamos en container, conectamos el worker
  # temporalmente a la red verify para alcanzar el ephemeral por DNS del
  # runtime. El cleanup desconecta antes de borrar la red (ver
  # `cleanup_ephemeral_pg`). Aplica igual con docker y podman.
  if [[ "$EN_DOCKER" == "1" ]]; then
    if ! "$CONTAINER_CMD" network connect "$BACKUP_VERIFY_NETWORK" "$WORKER_CONTAINER_ID" \
         >/dev/null 2>"$WORK_DIR/netconnect.err"; then
      report_failure "ephemeral_network_attach_failed:$(tail -c 200 "$WORK_DIR/netconnect.err" | tr '\n' ' ')"
    fi
  fi

  # codex P1 fix — host + puerto efectivos:
  #   * EN_DOCKER=1 → DNS del container (`copilotoia-verify-pg-$$`) + 5432 (sin port mapping).
  #   * EN_DOCKER=0 → 127.0.0.1 + puerto publicado al host.
  if [[ "$EN_DOCKER" == "1" ]]; then
    EPHEMERAL_HOST="$BACKUP_VERIFY_PG_CONTAINER"
    EPHEMERAL_PORT=5432
  else
    EPHEMERAL_HOST="127.0.0.1"
    EPHEMERAL_PORT="$BACKUP_VERIFY_PG_PORT"
  fi
  EPHEMERAL_PG_OK=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if PGPASSWORD="$BACKUP_VERIFY_SUPERUSER_PASSWORD" psql \
         "postgres://postgres@${EPHEMERAL_HOST}:${EPHEMERAL_PORT}/${VERIFY_DB}" \
         -Atc 'select 1' >/dev/null 2>&1; then
      EPHEMERAL_PG_OK=1
      break
    fi
    sleep 2
  done
  if [[ "$EPHEMERAL_PG_OK" != "1" ]]; then
    report_failure "ephemeral_pg_not_ready"
  fi

  # SEC-009 — Layer 3: provisionar el rol non-superuser. El restore usa
  # `backup_verifier` (sin SUPERUSER, REPLICATION, BYPASSRLS), con privilegios
  # mínimos sobre la DB de verificación.
  PGPASSWORD="$BACKUP_VERIFY_SUPERUSER_PASSWORD" psql \
    "postgres://postgres@${EPHEMERAL_HOST}:${EPHEMERAL_PORT}/${VERIFY_DB}" \
    -v ON_ERROR_STOP=1 -Atc "
      create role ${VERIFY_RESTORE_ROLE} login password '${BACKUP_VERIFY_RESTORE_PASSWORD}' nosuperuser noreplication nobypassrls nocreaterole nocreatedb;
      grant all on database ${VERIFY_DB} to ${VERIFY_RESTORE_ROLE};
      grant all on schema public to ${VERIFY_RESTORE_ROLE};
    " >/dev/null 2>"$WORK_DIR/role.err" || \
    report_failure "ephemeral_role_provision_failed:$(tail -c 200 "$WORK_DIR/role.err" | tr '\n' ' ')"

  VERIFY_URL="postgres://${VERIFY_RESTORE_ROLE}:${BACKUP_VERIFY_RESTORE_PASSWORD}@${EPHEMERAL_HOST}:${EPHEMERAL_PORT}/${VERIFY_DB}"
  # SEC-009.1-FU: el sufijo `:docker` / `:podman` aparece en
  # `audit_logs.metadata.restore_mode` para que el operador sepa qué runtime
  # ejecutó el restore real (útil para auditoría y para confirmar que el
  # fallback rootless está funcionando en hosts sin Docker daemon).
  RESTORE_MODE="ephemeral_isolated:${CONTAINER_CMD}"

  echo "==> Restaurando dump en Postgres efímero como ${VERIFY_RESTORE_ROLE}"
  if ! pg_restore --dbname="$VERIFY_URL" --no-owner --no-privileges --exit-on-error "$DUMP_PATH" >/dev/null 2>"$WORK_DIR/restore.err"; then
    report_failure "pg_restore_failed:$(tail -c 200 "$WORK_DIR/restore.err" | tr '\n' ' ')"
  fi
else
  # SEC-009.1-FU stop-gap — degraded mode cuando NI docker NI podman
  # están disponibles (host sin runtime de container). NO restaura: corre
  # `pg_restore --list` para validar parseability del dump, y reporta el
  # degraded mode en el audit log. La preferencia ahora es:
  #   1. `docker` con daemon respondiendo (modo legacy del compose)
  #   2. `podman` con daemon respondiendo (rootless, sin socket — hosts
  #      con políticas restrictivas que sí permiten podman rootless)
  #   3. degraded `pg_restore --list` (solo parseability)
  echo "==> [DEGRADED] Ni docker ni podman disponibles; corriendo pg_restore --list (SEC-009.1-FU)"
  if ! pg_restore --list "$DUMP_PATH" >"$WORK_DIR/restore.list" 2>"$WORK_DIR/restore.err"; then
    report_failure "pg_restore_list_failed:$(tail -c 200 "$WORK_DIR/restore.err" | tr '\n' ' ')"
  fi
  if [[ ! -s "$WORK_DIR/restore.list" ]]; then
    report_failure "pg_restore_list_empty"
  fi
  RESTORE_MODE="degraded_list_only"
fi

TENANTS_COUNT=0
CONVERSATIONS_COUNT=0
MESSAGES_COUNT=0
# SEC-009.1-FU: `RESTORE_MODE` ahora puede ser `ephemeral_isolated:docker` o
# `ephemeral_isolated:podman` (sufijo con el runtime). Comparamos por prefijo.
if [[ "$RESTORE_MODE" == ephemeral_isolated* ]]; then
  echo "==> Sanity checks"
  SANITY_SQL="
  select 'tenants', count(*) from copiloto_core.tenants
  union all select 'conversations', count(*) from copiloto_core.conversations
  union all select 'messages', count(*) from copiloto_core.messages
  "
  SANITY_OUT="$(psql "$VERIFY_URL" -Atc "$SANITY_SQL" 2>"$WORK_DIR/sanity.err" || true)"
  if [[ -z "$SANITY_OUT" ]]; then
    report_failure "sanity_query_failed:$(tail -c 200 "$WORK_DIR/sanity.err" | tr '\n' ' ')"
  fi

  TENANTS_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="tenants" {print $2}')"
  CONVERSATIONS_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="conversations" {print $2}')"
  MESSAGES_COUNT="$(echo "$SANITY_OUT" | awk -F'|' '$1=="messages" {print $2}')"

  # Schema fundamentally requires at least 1 tenant for a meaningful backup.
  if [[ -z "$TENANTS_COUNT" || "$TENANTS_COUNT" -lt 1 ]]; then
    report_failure "sanity_check_failed:tenants_count_is_${TENANTS_COUNT}"
  fi
else
  # SEC-009.1-FU stop-gap — degraded mode: contamos las tablas declaradas en el
  # listado del dump (no es equivalente a sanity real pero detecta dumps
  # truncados / sin schema `app`).
  TABLE_LINES="$(grep -c -E '^\S+ TABLE app\.' "$WORK_DIR/restore.list" || true)"
  if [[ -z "$TABLE_LINES" || "$TABLE_LINES" -lt 5 ]]; then
    report_failure "degraded_sanity_failed:table_count_is_${TABLE_LINES}"
  fi
fi

SIZE_BYTES="$(wc -c <"$ENC_PATH" | tr -d ' ')"

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -Atc "
  update app.backup_runs
     set status='ok',
         finished_at=now(),
         sha256='${LOCAL_SHA}',
         size_bytes=${SIZE_BYTES},
         metadata = metadata || jsonb_build_object(
           'tenants_count', ${TENANTS_COUNT:-0},
           'conversations_count', ${CONVERSATIONS_COUNT:-0},
           'messages_count', ${MESSAGES_COUNT:-0},
           'restore_mode', '${RESTORE_MODE}',
           'signature_verified', true
         )
   where id=:'run_id'::uuid
" >/dev/null

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" -Atc "
  insert into app.audit_logs (tenant_id, actor_type, action, entity_type, entity_id, metadata)
  values (
    null,
    'service',
    'backup.verified',
    'backup_runs',
    :'run_id'::uuid,
    jsonb_build_object(
      'evidence_path','${S3_URI}',
      'signature_path','${S3_URI_SIG}',
      'sha256','${LOCAL_SHA}',
      'restore_mode','${RESTORE_MODE}',
      'tenants_count', ${TENANTS_COUNT:-0},
      'conversations_count', ${CONVERSATIONS_COUNT:-0},
      'messages_count', ${MESSAGES_COUNT:-0}
    )
  )
" >/dev/null

echo "Backup verify OK [${RESTORE_MODE}]: tenants=${TENANTS_COUNT:-0} conversations=${CONVERSATIONS_COUNT:-0} messages=${MESSAGES_COUNT:-0}"
