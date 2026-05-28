# Grafana dashboards — CopilotoIA core

## Archivos

| Archivo | UID | Propósito |
|---------|-----|-----------|
| `core-health.json` | `copilotoia-core-health` | Salud operacional: pool DB, providers IA, backups |

## Importar

### Opción A — Provisioning (recomendado para CI/CD)

Montar este directorio como volumen en el container Grafana en
`/etc/grafana/provisioning/dashboards/` y agregar el provider config:

```yaml
# /etc/grafana/provisioning/dashboards/copilotoia.yaml
apiVersion: 1
providers:
  - name: copilotoia
    orgId: 1
    folder: CopilotoIA
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /etc/grafana/provisioning/dashboards/copilotoia
```

Cada JSON nuevo se importa automáticamente al reiniciar Grafana o
después de `updateIntervalSeconds`.

### Opción B — Import manual via UI

1. Grafana → Dashboards → New → Import.
2. Click "Upload JSON file" y elegir el `.json` del dashboard.
3. Seleccionar el datasource Prometheus al pegar la variable
   `${DS_PROMETHEUS}`.

## Métricas requeridas

Todas con prefijo `cpi_` (CopilotoIA), expuestas por `/metrics`
del proceso API:

```
cpi_db_pool_size         # gauge
cpi_db_pool_idle         # gauge
cpi_db_pool_min          # gauge
cpi_db_pool_max          # gauge
cpi_ai_provider_health   # gauge {provider, modality}
cpi_backup_last_success_age_seconds        # gauge {kind}
cpi_backup_last_verify_failed_age_seconds  # gauge {scope}
```

Ver `app/services/metrics.py` para el catálogo completo.

## Alertas vinculadas

El dashboard incluye links externos a runbooks. Las alertas que
los disparan viven en `infra/observability/alerts/core.yml`:

- `DbPoolExhausted` ↔ panel "DB pool — conexiones idle"
- `AiProviderDown` ↔ panel "AI providers — salud actual"
- `BackupStale` ↔ panel "Backup — edad del último éxito"
