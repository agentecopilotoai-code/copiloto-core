# Runbook — Token de Meta vencido o revocado

## Síntoma

- Alerta Prometheus `OutboundDLQGrowing` (>5 fallos en 5 min).
- Crecimiento sostenido del contador `cpi_outbound_dlq_total`.
- En el panel **Outbound DLQ** los items tienen `error_code='190'` y
  `error_title` con texto similar a *"Access token has expired"*.
- Mensajes outbound recientes en `messages` con `status='failed'` y
  `metadata->>'graph_error_code' = '190'`.

## Diagnóstico

```sql
-- ¿Cuántos fallos por canal en las últimas 4 h?
SELECT
  c.tenant_id,
  c.id AS channel_id,
  COUNT(*) FILTER (WHERE m.metadata->>'graph_error_code' = '190') AS token_expired,
  COUNT(*) FILTER (WHERE m.status = 'failed') AS total_failed
FROM app.messages m
JOIN app.tenant_channels c ON c.id = m.channel_id
WHERE m.created_at > now() - interval '4 hours'
GROUP BY c.tenant_id, c.id
ORDER BY token_expired DESC;
```

```bash
# Confirmar contra Graph API: si responde 190, el token está vencido.
curl -sS "https://graph.facebook.com/v19.0/${PHONE_NUMBER_ID}?access_token=${WHATSAPP_TOKEN}" \
  | jq '.error // "OK"'
```

## Mitigación inmediata

1. Generar un nuevo *System User Access Token* con permiso
   `whatsapp_business_messaging` en el Business Manager del tenant afectado.
2. Rotar el token desde el panel:
   `Admin Panel → Tenants → <slug> → Canales → WhatsApp → Rotar token`.
   El endpoint backend es `PATCH /v1/tenants/{tenant_id}/channels/{channel_id}`
   con `{"credentials": {"access_token": "<nuevo>"}}` (el valor se cifra antes
   de persistirse).
3. Reencolar los mensajes en DLQ:
   `Admin Panel → Operations Desk → Outbound DLQ → Reintentar todos`.
   Esto reescribe `messages.status='queued'` con un `idempotency_key` nuevo
   derivado del UUID original (ver `event_worker._retry_dlq`).
4. Verificar que el contador `cpi_outbound_dlq_total` deja de crecer y que
   `cpi_messages_total{direction="outbound",status="sent"}` se recupera.

## Fix definitivo

- Pasar el tenant a **System User token de larga duración** (no expira). Los
  tokens de usuario humano caducan a las 24 h y son frágiles.
- Habilitar `tenant_channels.token_expires_at` y la alerta
  `MetaTokenAboutToExpire` (regla pendiente — owner: integraciones).
- Documentar el responsable del token (campo `tenant_settings.owner_email`)
  para enrutar el siguiente recordatorio de rotación.

## Post-mortem checklist

- [ ] Token rotado y verificado contra Graph API.
- [ ] Mensajes en DLQ reencolados o descartados con razón documentada.
- [ ] Entrada en `audit_logs(action='channel.token_rotated')` confirmada.
- [ ] Notificación al manager del tenant (email automático vía
      `operator_alerts.kind='channel_degraded'`).
- [ ] Si la rotación tomó >1h, abrir incidente formal en `docs/incidents/`.
