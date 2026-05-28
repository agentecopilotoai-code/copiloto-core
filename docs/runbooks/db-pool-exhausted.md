# Runbook — DB pool exhausted (asyncpg)

**Alerta:** `DbPoolExhausted` (severity: page)
**Trigger:** `cpi_db_pool_idle == 0` por > 30s
**Categoría:** Infraestructura / DB

---

## Síntoma

- Latencia p99 de la API sube abruptamente.
- Algunos endpoints empiezan a devolver 504 / timeouts.
- Logs muestran `asyncpg.exceptions.PoolAcquireTimeoutError`.
- Gauge `cpi_db_pool_idle == 0` sostenido.

## Diagnóstico (en orden)

1. **¿La carga es legítima o un ataque?**

   ```promql
   sum(rate(http_requests_total[1m]))   # rps actual
   ```

   Comparar con el baseline histórico. Si rps es 5-10× lo normal,
   probablemente atacque o burst → ir a § Mitigación · ataque.

2. **¿Hay queries lentas bloqueando conexiones?**

   ```sql
   select pid, now() - query_start as duration, state, query
   from pg_stat_activity
   where state = 'active' and query_start < now() - interval '5s'
   order by duration desc limit 10;
   ```

   Si ves 1-2 queries con duration > 30s, probablemente bloqueo o
   missing index → ir a § Mitigación · query lenta.

3. **¿Hay locks?**

   ```sql
   select blocked_locks.pid as blocked_pid,
          blocking_locks.pid as blocking_pid,
          blocked_activity.query as blocked_query
   from pg_locks blocked_locks
   join pg_stat_activity blocked_activity on blocked_activity.pid = blocked_locks.pid
   join pg_locks blocking_locks
     on blocking_locks.locktype = blocked_locks.locktype
    and blocking_locks.granted
    and blocked_locks.pid <> blocking_locks.pid
   join pg_stat_activity blocking_activity on blocking_activity.pid = blocking_locks.pid
   where not blocked_locks.granted;
   ```

## Mitigación

### Caso A — Carga legítima

```bash
# Subir DB_POOL_MAX_SIZE en .env (verificar primero el max_connections
# de postgres para no overcommitear).
psql -h <host> -U postgres -c 'show max_connections;'

# Si max_connections >= (max_size_target × #workers + buffer 20):
kubectl set env deployment/copilotoia-api DB_POOL_MAX_SIZE=20
kubectl rollout status deployment/copilotoia-api
```

### Caso B — Query lenta

Identificar el PID y el query del paso 2, abortar:

```sql
select pg_terminate_backend(<pid>);
```

Después: agregar el index o reescribir el query. Si hay duda,
abrir ticket en el repo `[DB]` con el query plan (`EXPLAIN ANALYZE`).

### Caso C — Lock deadlock

Identificar quién bloquea (paso 3), abortar el bloqueador con
`pg_terminate_backend`. Investigar la TX para entender por qué
mantuvo el lock tanto tiempo (típicamente TX larga + commit lento o
spec roto).

### Caso D — Ataque

- Activar WAF/rate-limit en edge.
- Bloquear IPs ofensoras temporalmente en el firewall.
- Reportar a security@.

## Verificación

- `cpi_db_pool_idle > 3` por 5+ min.
- Latencia p99 vuelve al baseline.
- 0 errores `PoolAcquireTimeoutError` en los últimos 5 min.

## Postmortem

Documentar en `docs/incidents/<yyyy-mm-dd>-db-pool-exhausted.md` con:

- Inicio + fin del incidente
- Trigger (query, ataque, deploy reciente)
- Acción tomada
- Lecciones aprendidas

## Última revisión

2026-05-27 — TASK-PROD post audit#4.
