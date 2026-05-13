# Runbook — Postgres caído o degradado

## Síntoma

- Alerta `BotResponseLatencyP95High` sostenida (>10 min con p95 > 5s).
- `GET /healthz` devuelve `{"status":"unhealthy","postgres":"failing"}` o
  HTTP 503.
- `MetricsEndpointSilent` puede dispararse en paralelo si la API queda colgada
  esperando conexiones.
- Logs del API con `psycopg.OperationalError: could not connect to server`.

## Diagnóstico

```bash
# 1) ¿El contenedor está corriendo?
docker compose ps postgres

# 2) Logs recientes
docker compose logs --tail=200 postgres

# 3) Conectividad básica desde el host
docker compose exec postgres pg_isready -U copilotoia -d copilotoia
```

```sql
-- 4) Conexiones activas (si todavía responde).
SELECT state, COUNT(*) FROM pg_stat_activity GROUP BY state;

-- 5) Bloqueos / locks.
SELECT pid, age(clock_timestamp(), query_start), state, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start
LIMIT 20;

-- 6) Espacio en disco del WAL.
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')) AS wal_used;
```

## Mitigación inmediata

1. **Si Postgres responde pero está lento (locks o IO):**
   - Identificar la query culpable (`pg_stat_activity` ordenado por
     `query_start`) y cancelar con `SELECT pg_cancel_backend(<pid>);` o
     terminar con `pg_terminate_backend(<pid>)`.
   - Pausar `event-worker` y `campaign_worker` para reducir presión:
     `docker compose stop event-worker campaign_worker`.
2. **Si Postgres no responde:**
   - `docker compose restart postgres`.
   - Esperar a `pg_isready` exitoso (típicamente <30s en local).
   - Reanudar workers: `docker compose start event-worker campaign_worker`.
3. **Si el contenedor no levanta (disco lleno, corrupción):**
   - Liberar espacio (rotar logs, vaciar `/var/log`).
   - Restaurar desde último backup cloud:
     ```bash
     scripts/restore-from-cloud.sh --date YYYY-MM-DD --target ./restore.dump
     pg_restore -h localhost -U copilotoia -d copilotoia_restore ./restore.dump
     ```
     Ver `docs/backup-policy.md` para el procedimiento completo.
4. Anunciar la degradación en el canal del cliente afectado (campo
   `tenants.support_channel`) y registrar inicio en `operator_alerts(kind='database_down')`.

## Fix definitivo

- Provisionar replica de lectura + standby con replicación lógica para
  failover automático.
- Migrar a Postgres gestionado (RDS / Cloud SQL) si el incidente lo provocó
  un problema de I/O del host.
- Revisar índices faltantes en la query más lenta y añadirlos via migración.
- Bajar el `statement_timeout` del API para que un query lento no monopolice
  el pool.

## Post-mortem checklist

- [ ] Causa raíz documentada (query, disco, OOM, fallo de hardware).
- [ ] Tiempo total de downtime registrado.
- [ ] Último backup verificado contra el RPO (≤ 24 h).
- [ ] Tickets de seguimiento abiertos para el fix definitivo.
- [ ] Si afectó >1 tenant: notificación masiva con resumen y acciones.
