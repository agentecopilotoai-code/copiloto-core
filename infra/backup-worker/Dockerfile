# TASK-0064 / SEC-009 — Imagen del backup-worker.
#
# Provee `pg_dump`/`psql`, `gpg`, `aws` CLI, `docker` CLI, `openssl` y `cron`
# en un container minimal para ejecutar scripts/backup-to-cloud.sh diariamente
# y scripts/verify-backup.sh semanalmente. El docker CLI se usa SOLO desde el
# verifier para spin-up del Postgres efímero isolated (SEC-009 Layer 2). El
# fallback `BACKUP_VERIFY_SKIP_EPHEMERAL=1` permite operar sin el socket.
FROM postgres:16-bookworm

# Install GPG + AWS CLI + cron + docker CLI + openssl en una sola capa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cron \
        curl \
        docker.io \
        gnupg2 \
        openssl \
        unzip \
    && curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip /var/lib/apt/lists/*

WORKDIR /app

COPY infra/backup-worker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY infra/backup-worker/crontab /etc/cron.d/copilotoia-backup
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && chmod 0644 /etc/cron.d/copilotoia-backup \
    && crontab /etc/cron.d/copilotoia-backup

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
