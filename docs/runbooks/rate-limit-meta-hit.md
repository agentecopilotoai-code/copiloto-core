# Runbook — Rate limit de Meta golpeado (error 80007)

## Síntoma

- Alerta `HighOutboundErrorRate` (>5% fallos en 5 min).
- En la DLQ outbound aparecen items con `error_code='80007'` o
  `error_title` *"Rate limit hit"*.
- `cpi_circuit_breaker_state{provider="meta_graph"}` oscila entre 1 y 2.
- El throughput outbound cae bruscamente aunque la cola siga llena.

## Diagnóstico

```sql
-- Distribución de error_code en la DLQ (últimas 2 h). El worker persiste el
-- code de Meta tal cual en la columna app.messages.error_code; ver
-- ``delivery_error_code`` en app/workers/event_worker.py.
SELECT
  COALESCE(NULLIF(m.error_code, ''), 'transport_error') AS error_code,
  COUNT(*) AS occurrences
FROM app.messages m
WHERE m.status = 'failed'
  AND m.created_at > now() - interval '2 hours'
  AND m.direction = 'outbound'
GROUP BY 1
ORDER BY occurrences DESC;
```

```sql
-- Throughput actual por tenant_channel (mensajes/min). messages no tiene
-- channel_id propio; se deriva vía conversations → tenant_channels.
SELECT
  cv.channel_id,
  date_trunc('minute', m.created_at) AS minute,
  COUNT(*)
FROM app.messages m
JOIN app.conversations cv ON cv.id = m.conversation_id
WHERE m.direction = 'outbound'
  AND m.created_at > now() - interval '30 minutes'
GROUP BY cv.channel_id, minute
ORDER BY minute DESC, cv.channel_id;
```

```sql
-- Tier del canal (Meta limita por tier: 1K / 10K / 100K / 1M conversaciones/24h).
SELECT id, phone_number_id, quality_rating, messaging_limit_tier, status
FROM app.tenant_channels
WHERE id = '<channel_id>';
```

## Mitigación inmediata

1. **Pausar campañas en curso** para liberar capacidad outbound para
   mensajería transaccional. El status válido en `app.campaigns` para detener
   un envío es `cancelled` (ver CHECK del schema):
   ```sql
   UPDATE app.campaigns
   SET status = 'cancelled', updated_at = now()
   WHERE status = 'running' AND tenant_id = '<tenant_id>';
   ```
2. **Reducir paralelismo** del worker para que Meta se enfríe:
   ```bash
   docker compose up -d --scale event-worker=1
   ```
   Volver a la escala baseline una vez `cpi_messages_total{status="sent"}`
   se recupere.
3. **Subir el cooldown del circuit breaker** (env var, requiere reinicio del
   `api` y `event-worker`):
   ```bash
   # En .env o docker-compose.yml:
   CIRCUIT_BREAKER_COOLDOWN_SECONDS=60
   ```
   Default = 30s. Subir a 60–120s evita el flapping mientras Meta sigue
   limitando.
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
