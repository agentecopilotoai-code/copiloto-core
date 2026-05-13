# Runbook — Rate limit de Meta golpeado (error 80007)

## Síntoma

- Alerta `HighOutboundErrorRate` (>5% fallos en 5 min).
- En la DLQ outbound aparecen items con `error_code='80007'` o
  `error_title` *"Rate limit hit"*.
- `cpi_circuit_breaker_state{provider="meta_graph"}` oscila entre 1 y 2.
- El throughput outbound cae bruscamente aunque la cola siga llena.

## Diagnóstico

```sql
-- Distribución de error_code en la DLQ (últimas 2 h).
SELECT
  m.metadata->>'graph_error_code' AS error_code,
  COUNT(*) AS occurrences
FROM app.messages m
WHERE m.status = 'failed'
  AND m.created_at > now() - interval '2 hours'
  AND m.direction = 'outbound'
GROUP BY 1
ORDER BY occurrences DESC;
```

```sql
-- Throughput actual por canal (mensajes/min).
SELECT
  m.channel_id,
  date_trunc('minute', m.created_at) AS minute,
  COUNT(*)
FROM app.messages m
WHERE m.direction = 'outbound'
  AND m.created_at > now() - interval '30 minutes'
GROUP BY m.channel_id, minute
ORDER BY minute DESC, m.channel_id;
```

```bash
# Tier del canal (Meta limita por tier: 1K / 10K / 100K / 1M conversaciones/24h).
docker compose exec api python -m app.tools.show_channel_tier --channel <id>
```

## Mitigación inmediata

1. **Reducir rate del scheduler** en caliente:
   ```bash
   docker compose exec api \
     python -m app.tools.set_runtime_config \
       --key event_worker.outbound_rate_per_second --value 5
   ```
   Valor previo típico: 20/s. Reduce a 5/s mientras Meta se enfría.
2. **Aumentar backoff exponencial**: setear `event_worker.retry_backoff_base`
   a `4` (segundos) en lugar de `2`.
3. Pausar campañas en curso para liberar capacidad para mensajería
   transaccional:
   ```sql
   UPDATE app.campaigns SET status = 'paused'
   WHERE status = 'running' AND tenant_id = '<tenant_id>';
   ```
4. Reencolar la DLQ una vez que el throughput se estabilice (Operations Desk
   → Outbound DLQ → Reintentar).

## Fix definitivo

- Solicitar upgrade de tier a Meta (requiere historial de quality_rating
  GREEN y volumen sostenido).
- Implementar **token bucket por canal** (no solo global) en
  `event_worker.send_message`, dimensionado a tier real del canal.
- Distribuir el envío por horas: mover campañas a slots de baja demanda usando
  `campaigns.schedule_window`.
- Alertar antes con un `MetaRateLimitWarning` cuando el ratio 80007 supere
  1% durante 2 min (regla pendiente — owner: integraciones).

## Post-mortem checklist

- [ ] Verificar que el rate volvió al valor estándar tras el incidente.
- [ ] Documentar el pico (mensajes/min observados vs tier del canal).
- [ ] Confirmar que la cola del scheduler drenó por completo.
- [ ] Si afectó SLA: notificación al manager del tenant con resumen.
