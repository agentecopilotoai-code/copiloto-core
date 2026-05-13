# TASK-0064 — Imagen del backup-worker.
#
# Provee `pg_dump`/`psql`, `gpg`, `aws` CLI y `cron` en un container minimal
# para ejecutar scripts/backup-to-cloud.sh diariamente y scripts/verify-backup.sh
# semanalmente.
FROM postgres:16-bookworm

# Install GPG + AWS CLI + cron en una sola capa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        cron \
        curl \
        gnupg2 \
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
