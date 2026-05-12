# Plantilla de evidencia de go-live por tenant

Copiar y completar una instancia de esta plantilla por cada tenant que avance a producción.
El script `scripts/go-live-runbook.sh` genera automáticamente la sección de resultados.

---

## Evidencia de go-live — `<tenant_slug>` (`<tenant_id>`)

| Campo           | Valor                              |
|-----------------|------------------------------------|
| Tenant ID       | `<uuid>`                           |
| Tenant slug     | `<slug>`                           |
| Responsable     | `<nombre y cargo>`                 |
| Fecha inicio    | `YYYY-MM-DDTHH:MM:SSZ`             |
| Fecha fin       | `YYYY-MM-DDTHH:MM:SSZ`             |
| Resultado       | APROBADO / BLOQUEADO               |
| Readiness       | ready / not_ready                  |
| Canal WA status | healthy / degraded / not_found     |
| account_mode    | mock / live                        |
| RAG sufficient  | true / false                       |
| RAG top_score   | `<float>`                          |
| Checks ok       | `<n>`                              |
| Checks fallidos | `<n>`                              |

### Checks individuales

| Check                          | Estado | Razón                                   |
|--------------------------------|--------|-----------------------------------------|
| Tenant activo                  | ✓ / ✗  |                                         |
| Settings operativos            | ✓ / ✗  |                                         |
| Canal WhatsApp                 | ✓ / ✗  |                                         |
| Documentos activos y retrieval | ✓ / ✗  |                                         |
| Handoff humano                 | ✓ / ✗  |                                         |
| Auditoría                      | ✓ / ✗  |                                         |

### Bloqueos

<!-- Lista de bloqueos detectados o "Ninguno." -->

### Notas del operador

<!-- Observaciones adicionales, screenshots, contexto relevante -->

### Rollback ejecutado

<!-- Si se ejecutó rollback: fecha, razón y comando utilizado.
     Ejemplo:
     - Fecha: 2026-05-09T14:32:00Z
     - Razón: Canal en modo mock por error de token Meta
     - Comando: scripts/go-live-runbook.sh --tenant <uuid> --responsible "Raul M." --rollback-to-mock "Token inválido"
-->

---

## Cómo ejecutar el runbook

```bash
# Ejecución estándar (requiere API levantada)
TENANT_ID=<uuid> \
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --smoke-question "precios manicure servicios disponibles"

# Con tokens Auth0 reales (cuando AUTH0_DOMAIN está configurado)
RUNBOOK_ADMIN_TOKEN=<token_real> \
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --api https://api.copilotoia.com

# Rollback operativo: volver a modo mock sin SQL
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --rollback-to-mock "Rollback preventivo: fallo en prueba de envío"
```

## Procedimiento de rollback completo

Si el go-live debe revertirse después de activar tráfico real:

1. **Cambiar canal a mock** (sin SQL): ejecutar el comando `--rollback-to-mock` de arriba.
2. **Pausar bot / forzar handoff**: ir a Operations Desk → conversación activa → forzar handoff humano.
3. **Verificar readiness post-rollback**: ejecutar el runbook de nuevo; el check `account_mode=live` fallará (esperado).
4. **Documentar**: completar la sección "Rollback ejecutado" arriba con fecha y razón.

> **Diferencia importante:**
> - `tenant.status = active`: el tenant existe y puede operar en la plataforma.
> - `channel.account_mode = live`: los mensajes salientes se envían realmente a Meta/WhatsApp.
> Ambos deben estar activos para tráfico real, pero se controlan de forma independiente.

---

*Generado por `scripts/go-live-runbook.sh`. Última actualización de plantilla: 2026-05-08.*

---

## Drill de restore local — TASK-0029 (cierre operacional de TASK-0015)

Validación end-to-end de `scripts/backup-local.sh` y `scripts/restore-local.sh`
contra Docker Compose con datos demo.

| Campo                        | Valor                                                                         |
|------------------------------|-------------------------------------------------------------------------------|
| Fecha (UTC)                  | 2026-05-12T03:21Z                                                             |
| Entorno                      | Docker `pgvector/pgvector:pg16` (servicio `postgres` de `docker-compose.yml`) |
| Backup directory             | `backups/local/20260512T032110Z`                                              |
| Tamaño de `postgres.dump`    | 168 758 bytes                                                                 |
| SHA-256 de `postgres.dump`   | `f7237256ce088aee4e58ca3a1879ce816c60fbd549fd4a07152de9ee4aea3ee8`            |
| Knowledge files (volumen)    | No aplicó: servicio `api` no estaba corriendo (sandbox sin acceso a apt repo) |
| Resultado                    | APROBADO — `restore-local.sh` validó conteos automáticamente                  |

### Datos demo sembrados antes del backup

Sobre la base ya inicializada por `infra/postgres/02-seed.sql` (3 tenants, 3 settings,
3 channels), se insertaron datos operativos de ejercicio:

- 2 contactos en `demo-barberia` con `opt_in_status = granted`.
- 2 conversaciones (1 abierta, 1 cerrada) con su canal por defecto.
- 4 mensajes (`inbound contact` + `outbound bot/agent`) y 1 `message_status_events`.
- 2 documentos de conocimiento (`Horarios`, `Servicios`) con 4 chunks asociados.
- 1 `audit_logs` y 1 `domain_events` rotulados como `drill.*`.

### Conteos antes vs. después del restore

Tomados con `psql` como `copiloto_admin` para evitar el filtro RLS por tenant.

| Tabla                  | Backup (`table-counts.tsv`) | Post-`down -v` (DB limpia con seeds) | Post-restore | OK |
|------------------------|------:|------:|------:|----|
| audit_logs             | 1 | 0 | 1 | ✓ |
| contacts               | 2 | 0 | 2 | ✓ |
| conversations          | 2 | 0 | 2 | ✓ |
| domain_events          | 1 | 0 | 1 | ✓ |
| knowledge_chunks       | 4 | 0 | 4 | ✓ |
| knowledge_documents    | 2 | 0 | 2 | ✓ |
| messages               | 4 | 0 | 4 | ✓ |
| message_status_events  | 1 | 0 | 1 | ✓ |
| tenant_channels        | 3 | 3 | 3 | ✓ |
| tenants                | 3 | 3 | 3 | ✓ |
| tenant_settings        | 3 | 3 | 3 | ✓ |

`restore-local.sh` ejecuta `diff -u` entre `table-counts.tsv` del backup y los
conteos post-restore; el script terminó con
`Restore local validado: conteos, tenants, documentos, chunks y audit logs coinciden.`

### Bug detectado y corregido durante el drill

`backup-local.sh` invocaba `pg_dump … --file=- > postgres.dump`. En `pg_dump`,
`--file=-` no es alias de stdout: se interpreta como un archivo literal llamado
`-` dentro del contenedor, por lo que el redirect host capturaba un archivo de
**0 bytes** sin que `set -euo pipefail` lo detectara. El restore fallaba con
`pg_restore: error: did not find magic string in file header`.

**Fix aplicado:** se eliminó `--file=-` (usando stdout por omisión) y se agregó
una verificación `[[ ! -s "$BACKUP_DIR/postgres.dump" ]]` que aborta si el dump
queda vacío. Cubierto por la regresión
`tests/test_backup_restore_scripts_static.py::test_backup_script_does_not_use_pg_dump_file_dash`.

### Cómo se reprodujo el drill

```bash
# 1. Levantar postgres y aplicar seeds (en este sandbox la build de api/event-worker
#    falla por bloqueo de deb.debian.org; se usa solo el servicio postgres).
docker compose up -d postgres

# 2. Sembrar datos operativos demo (contactos, conversaciones, mensajes, knowledge).
docker compose exec -T postgres psql "$DATABASE_URL" -f /tmp/drill-seed.sql

# 3. Backup.
./scripts/backup-local.sh
#   → backups/local/20260512T032110Z/{postgres.dump,table-counts.tsv,manifest.json,…}

# 4. Reset de la base (equivalente a bootstrap.sh --reset --yes --skip-smoke).
docker compose down -v --remove-orphans
docker compose up -d postgres

# 5. Restore + validación automática de conteos.
./scripts/restore-local.sh backups/local/20260512T032110Z

# 6. Pruebas estáticas (incluye bash -n y la regresión del bug `--file=-`).
python -m pytest tests/test_backup_restore_scripts_static.py -v
```

### Limitaciones del entorno

El sandbox no permitió construir las imágenes `api`, `event-worker`,
`scheduler` (apt-get rechazado por `deb.debian.org`), por lo que el bloque del
script que tar/untar el volumen `/app/data/knowledge` no se ejercitó: ambos
scripts ya tienen el camino "api no corriendo → omitir tar" probado por el
drill (genera `knowledge-files.sha256` vacío y `knowledge_files_tar=null` en
el manifiesto, sin abortar). Ejecutar el drill con la API levantada queda
recomendado para staging o cualquier ambiente con build network completa.
