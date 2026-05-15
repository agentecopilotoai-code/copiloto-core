"""Static tests for SEC-009 — Backup verification trust model.

Coverage:
 1. Producer (`scripts/backup-to-cloud.sh`) requires `BACKUP_SIGNER_FPR` and
    signs the encrypted blob with `gpg --detach-sign` after encryption.
 2. Producer uploads the detached signature as a sibling `.sig` object and the
    monthly snapshot copies both the dump and its signature.
 3. Producer fails closed if the signer private key is missing on disk.
 4. Verifier (`scripts/verify-backup.sh`) requires
    `BACKUP_SIGNER_PUBKEY_PATH` and aborts at startup if the file is absent.
 5. Verifier downloads the `.sig` sibling and `gpg --verify`s BEFORE any
    `gpg --decrypt`. Source-order is asserted explicitly.
 6. Verifier does NOT trust `Metadata.sha256` as authoritative anymore (no
    `sha256_mismatch` short-circuit between download and decrypt).
 7. Verifier restores into an isolated ephemeral Postgres container with a
    bridge `--internal` network — does NOT target `POSTGRES_HOST=postgres`
    for the restore step.
 8. Restore role is `backup_verifier` (non-superuser) — not `postgres`.
 9. Provisioned role is `nosuperuser noreplication nobypassrls`.
10. A degraded mode (`BACKUP_VERIFY_SKIP_EPHEMERAL=1`) is documented and falls
    back to `pg_restore --list` only — flagged as SEC-009.1-FU.
11. `infra/backup-worker/Dockerfile` installs the docker CLI and openssl.
12. `infra/backup-worker/entrypoint.sh` exports the new env vars and imports
    the signer pubkey at boot.
13. `docker-compose.yml` mounts the docker socket on the verifier service and
    exposes the new `BACKUP_SIGNER_*` env vars.
14. Runbook `docs/runbooks/backup-signature-setup.md` exists and covers
    key generation, distribution, rotation and the degraded mode.
15. Both scripts pass `bash -n`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _producer() -> str:
    return (ROOT / 'scripts' / 'backup-to-cloud.sh').read_text(encoding='utf-8')


def _verifier() -> str:
    return (ROOT / 'scripts' / 'verify-backup.sh').read_text(encoding='utf-8')


def _dockerfile() -> str:
    return (ROOT / 'infra' / 'backup-worker' / 'Dockerfile').read_text(encoding='utf-8')


def _entrypoint() -> str:
    return (ROOT / 'infra' / 'backup-worker' / 'entrypoint.sh').read_text(encoding='utf-8')


def _compose() -> str:
    return (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')


def _runbook() -> str:
    return (ROOT / 'docs' / 'runbooks' / 'backup-signature-setup.md').read_text(encoding='utf-8')


# --------------------------------------------------------------------------- #
# Producer (backup-to-cloud.sh)                                               #
# --------------------------------------------------------------------------- #


def test_producer_requires_signer_fingerprint_and_signs_after_encrypt() -> None:
    script = _producer()
    assert 'require_var BACKUP_SIGNER_FPR' in script, \
        'SEC-009: producer must require BACKUP_SIGNER_FPR'
    # detach-sign command present.
    assert 'gpg --batch --yes \\\n      --local-user "$BACKUP_SIGNER_FPR" \\\n      --output "$SIG_PATH" \\\n      --detach-sign --armor "$ENC_PATH"' in script, \
        'SEC-009: producer must detach-sign with the signer key over the encrypted blob'
    # And it must happen AFTER the encrypt step (sign of the ciphertext, not the dump).
    encrypt_idx = script.index('--encrypt "$DUMP_PATH"')
    sign_idx = script.index('--detach-sign --armor "$ENC_PATH"')
    assert sign_idx > encrypt_idx, 'SEC-009: detach-sign must follow encrypt (signs the ciphertext)'


def test_producer_uploads_sibling_signature_and_preserves_it_monthly() -> None:
    script = _producer()
    assert 'S3_KEY_SIG="${S3_KEY}.sig"' in script
    assert 'aws "${AWS_CLI_ARGS[@]}" s3 cp "$SIG_PATH" "$S3_URI_SIG"' in script
    # Monthly snapshot copies the signature too.
    assert 'MONTHLY_SIG_KEY="${MONTHLY_KEY}.sig"' in script
    assert 's3 cp "$S3_URI_SIG" "s3://${BACKUP_S3_BUCKET}/${MONTHLY_SIG_KEY}"' in script


def test_producer_fails_closed_if_signer_privkey_missing() -> None:
    script = _producer()
    assert 'if [[ ! -f "$BACKUP_SIGNER_PRIVKEY_PATH" ]]; then' in script
    assert 'clave privada del signer no encontrada' in script


# --------------------------------------------------------------------------- #
# Verifier (verify-backup.sh) — Layer 1: GPG detached signature              #
# --------------------------------------------------------------------------- #


def test_verifier_requires_signer_pubkey_and_aborts_when_absent() -> None:
    script = _verifier()
    assert 'BACKUP_SIGNER_PUBKEY_PATH="${BACKUP_SIGNER_PUBKEY_PATH:-/app/.secrets/backup_signer_pubkey.asc}"' in script
    assert 'if [[ ! -f "$BACKUP_SIGNER_PUBKEY_PATH" ]]; then' in script
    assert 'pubkey del signer no encontrada' in script


def test_verifier_runs_gpg_verify_before_any_gpg_decrypt() -> None:
    script = _verifier()
    verify_idx = script.index('gpg --batch --status-fd 1 --verify "$SIG_PATH" "$ENC_PATH"')
    decrypt_idx = script.index('gpg --batch --yes --quiet --output "$DUMP_PATH" --decrypt "$ENC_PATH"')
    assert verify_idx < decrypt_idx, \
        'SEC-009: gpg --verify must precede gpg --decrypt (otherwise we decrypt untrusted input)'
    # GOODSIG defense in depth.
    assert "grep -q '^\\[GNUPG:\\] GOODSIG ' \"$WORK_DIR/verify.out\"" in script
    # Failure paths emit explicit reasons.
    assert 'gpg_verify_failed' in script
    assert 'gpg_verify_no_goodsig' in script
    assert 'missing_detached_signature:sec_009_fail_closed' in script


def test_verifier_no_longer_trusts_s3_metadata_sha256() -> None:
    script = _verifier()
    # The old short-circuit "sha256_mismatch" gate is gone.
    assert 'sha256_mismatch' not in script, \
        'SEC-009: trusting Metadata.sha256 from the bucket writer is the bug — must be removed'
    # And we don't call head-object Query 'Metadata.sha256' anymore for trust decisions.
    assert "head-object" not in script, \
        'SEC-009: head-object/Metadata.sha256 must not gate the verify path'


# --------------------------------------------------------------------------- #
# Verifier — Layer 2: ephemeral isolated Postgres                            #
# --------------------------------------------------------------------------- #


def test_verifier_restores_into_ephemeral_isolated_postgres_not_productive_cluster() -> None:
    script = _verifier()
    # Layer 2 — ephemeral container spin up.
    assert 'docker run -d --rm' in script
    assert 'BACKUP_VERIFY_PG_IMAGE' in script
    assert 'BACKUP_VERIFY_NETWORK' in script
    # --internal network ensures the ephemeral PG cannot reach the productive cluster.
    assert 'docker network create --driver bridge --internal "$BACKUP_VERIFY_NETWORK"' in script
    # Restore target is the ephemeral host:port, NOT POSTGRES_HOST.
    assert 'EPHEMERAL_HOST="127.0.0.1"' in script
    assert 'postgres://${VERIFY_RESTORE_ROLE}:${BACKUP_VERIFY_RESTORE_PASSWORD}@${EPHEMERAL_HOST}:${BACKUP_VERIFY_PG_PORT}/${VERIFY_DB}' in script
    # We do NOT createdb / dropdb against POSTGRES_HOST anymore.
    assert 'createdb -h "$PG_HOST" -U postgres' not in script
    assert 'dropdb -h "$PG_HOST" -U postgres' not in script
    # And the previous "VERIFY_URL=postgres://postgres@${PG_HOST}/..." pattern is gone.
    assert 'postgres://postgres@${PG_HOST}' not in script


# --------------------------------------------------------------------------- #
# Verifier — Layer 3: non-superuser restore role                             #
# --------------------------------------------------------------------------- #


def test_verifier_uses_non_superuser_restore_role() -> None:
    script = _verifier()
    assert 'VERIFY_RESTORE_ROLE="backup_verifier"' in script
    # Role created with minimal privileges.
    assert 'nosuperuser noreplication nobypassrls nocreaterole nocreatedb' in script
    # The restore connection string uses backup_verifier, not postgres.
    assert '${VERIFY_RESTORE_ROLE}:${BACKUP_VERIFY_RESTORE_PASSWORD}' in script


# --------------------------------------------------------------------------- #
# Verifier — Degraded mode (SEC-009.1-FU)                                    #
# --------------------------------------------------------------------------- #


def test_verifier_documents_degraded_mode_for_no_docker_socket() -> None:
    script = _verifier()
    assert 'BACKUP_VERIFY_SKIP_EPHEMERAL' in script
    assert 'SEC-009.1-FU' in script
    assert 'pg_restore --list' in script
    assert "RESTORE_MODE=\"degraded_list_only\"" in script
    # Audit log records the restore mode.
    assert "'restore_mode'," in script
    assert "'signature_verified', true" in script


# --------------------------------------------------------------------------- #
# Infra wiring                                                               #
# --------------------------------------------------------------------------- #


def test_dockerfile_installs_docker_cli_and_openssl() -> None:
    df = _dockerfile()
    assert 'docker.io' in df, 'SEC-009 Layer 2 needs docker CLI inside the verifier container'
    assert 'openssl' in df, 'verifier uses openssl to generate ephemeral passwords'


def test_entrypoint_exports_signer_env_vars_and_imports_pubkey() -> None:
    ep = _entrypoint()
    assert 'BACKUP_SIGNER_FPR' in ep
    assert 'BACKUP_SIGNER_PRIVKEY_PATH' in ep
    assert 'BACKUP_SIGNER_PUBKEY_PATH' in ep
    # Pubkey is imported at boot so the cron job is ready without re-importing.
    assert 'gpg --batch --quiet --import "${BACKUP_SIGNER_PUBKEY_PATH:-/app/.secrets/backup_signer_pubkey.asc}"' in ep


def test_compose_mounts_docker_socket_and_exposes_signer_env() -> None:
    compose = _compose()
    assert 'BACKUP_SIGNER_FPR:' in compose
    assert 'BACKUP_SIGNER_PUBKEY_PATH:' in compose
    assert 'BACKUP_VERIFY_NETWORK:' in compose
    assert '/var/run/docker.sock:/var/run/docker.sock' in compose


# --------------------------------------------------------------------------- #
# Runbook                                                                    #
# --------------------------------------------------------------------------- #


def test_runbook_covers_key_generation_distribution_rotation_and_degraded() -> None:
    doc = _runbook()
    assert 'gpg --batch --gen-key' in doc
    assert 'backup_signer_pubkey.asc' in doc
    assert 'backup_signer_privkey.asc' in doc
    assert 'BACKUP_SIGNER_FPR' in doc
    # Rotation covered.
    assert 'Rotación' in doc or 'rotacion' in doc.lower()
    # Degraded mode documented + FU ticket.
    assert 'BACKUP_VERIFY_SKIP_EPHEMERAL' in doc
    assert 'SEC-009.1-FU' in doc
    # Explicit warning about not storing the pubkey in the bucket.
    assert 'no debe' in doc.lower() and 'bucket' in doc.lower()


# --------------------------------------------------------------------------- #
# Bash syntax                                                                #
# --------------------------------------------------------------------------- #


def test_scripts_pass_bash_syntax_check() -> None:
    bash = shutil.which('bash')
    assert bash is not None
    for name in ('backup-to-cloud.sh', 'verify-backup.sh'):
        result = subprocess.run(
            [bash, '-n', str(ROOT / 'scripts' / name)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, f'{name}: {result.stderr}'
