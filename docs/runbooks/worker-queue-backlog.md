# Runbook — Cola de workers acumulada

## Síntoma

- Alerta `WorkerQueueBacklog`: `cpi_worker_queue_depth > 1000` durante 5 min.
- O alerta `SchedulerBehind` para `worker="scheduler"`.
- Mensajes outbound retrasados, recordatorios llegando tarde, conversaciones
  con respuesta tardía.

## Diagnóstico

```bash
# 1) Depth de cada cola.
curl -sS http://localhost:8000/metrics | grep cpi_worker_queue_depth

# 2) ¿Cuántas réplicas hay corriendo?
docker compose ps event-worker

# 3) Uso de CPU/RAM del worker.
docker stats --no-stream | grep -E "event-worker|scheduler|campaign_worker"
```

```sql
-- Mensajes 'queued' u 'enqueued' por más de 5 min.
SELECT
  status,
  COUNT(*) AS pending,
  MIN(created_at) AS oldest,
  MAX(created_at) AS newest
FROM app.messages
WHERE direction = 'outbound'
  AND status IN ('queued', 'enqueued')
  AND created_at < now() - interval '5 minutes'
GROUP BY status;
```

```sql
-- Jobs del scheduler atrasados.
SELECT kind, COUNT(*) AS pending, MIN(run_at) AS oldest
FROM app.scheduled_jobs
WHERE run_at < now()
  AND status = 'pending'
GROUP BY kind
ORDER BY pending DESC;
```

## Mitigación inmediata

1. **Escalar `event-worker` horizontalmente:**
   ```bash
   docker compose up -d --scale event-worker=4
   ```
   Cada réplica es stateless y consume del mismo channel Redis con `XREADGROUP`,
   así que añadir réplicas drena la cola en paralelo. Subir hasta 8 si el
   backlog supera 10 000.
2. **Pausar workers no críticos** para liberar conexiones a Postgres:
   ```bash
   docker compose stop campaign_worker digest_worker
   ```
   Reanudar tras drenar la cola crítica.
3. Verificar que el provider downstream (Meta, Stripe) no está limitado: si
   el problema es upstream, escalar el worker no ayuda — ver
   [rate-limit-meta-hit.md](rate-limit-meta-hit.md).
4. Si el backlog crece más rápido que el drain con 8 réplicas → activar
   degraded mode: rechazar campañas nuevas (`tenant_settings.campaigns_enabled
   = false`) hasta que se estabilice.

## Fix definitivo

- Habilitar **auto-scaling** del worker (HPA en k8s o `docker compose
  --scale` automatizado vía métrica de depth).
- Particionar el stream Redis por tenant para evitar que un tenant ruidoso
  bloquee a otros (consumer group por tenant).
- Bajar el batch size del worker si los items son CPU-bound; subirlo si son
  IO-bound.
- Migrar jobs del scheduler a tabla particionada por día para evitar
  degradación de queries con `run_at` cuando la tabla crece.

## Post-mortem checklist

- [ ] Cola drenada (depth <100 sostenido durante 10 min).
- [ ] Réplicas devueltas al baseline tras estabilizar.
- [ ] Tiempo total de retraso documentado (oldest pending - now).
- [ ] Si afectó SLA: comunicación a los tenants impactados.
- [ ] Si fue causa única (deploy mal hecho, query lenta): post-mortem
      detallado en `docs/incidents/`.
