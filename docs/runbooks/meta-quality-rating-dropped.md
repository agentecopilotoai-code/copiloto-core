# Runbook — Quality rating de Meta cayó a RED/YELLOW

## Síntoma

- `tenant_channels.quality_rating` quedó en `'RED'` o `'YELLOW'` tras un
  webhook `account_update` o `message_template_quality_update` de Meta.
- Caída en `cpi_messages_total{direction="outbound",status="sent"}` para ese
  tenant; Meta reduce su throughput automáticamente.
- Recepción del email/whatsapp de `operator_alerts` con
  `kind='channel_quality_dropped'`.

## Diagnóstico

```sql
-- Estado actual del canal y plantillas activas.
SELECT
  tc.tenant_id,
  tc.id AS channel_id,
  tc.quality_rating,
  tc.messaging_limit_tier,
  tc.updated_at,
  COUNT(t.id) FILTER (WHERE t.status='approved' AND t.category='UTILITY') AS utility_templates,
  COUNT(t.id) FILTER (WHERE t.status='approved' AND t.category='MARKETING') AS marketing_templates
FROM app.tenant_channels tc
LEFT JOIN app.whatsapp_templates t ON t.tenant_id = tc.tenant_id
WHERE tc.id = '<channel_id>'
GROUP BY tc.tenant_id, tc.id, tc.quality_rating, tc.messaging_limit_tier, tc.updated_at;
```

```sql
-- Volumen de templates MARKETING en las últimas 24h (suelen disparar el flag).
SELECT t.name, t.category, COUNT(*) AS sent_24h
FROM app.messages m
JOIN app.whatsapp_templates t
  ON t.id = (m.metadata->>'template_id')::uuid
WHERE m.created_at > now() - interval '24 hours'
  AND m.direction = 'outbound'
GROUP BY t.name, t.category
ORDER BY sent_24h DESC
LIMIT 20;
```

## Mitigación inmediata

1. **Pausar todas las campañas activas** del tenant:
   ```sql
   UPDATE app.campaigns
   SET status = 'paused', updated_at = now()
   WHERE tenant_id = '<tenant_id>' AND status = 'running';
   ```
2. Pausar el `campaign_worker` para ese tenant si la cola sigue drenando:
   `Admin Panel → Campañas → Pausar todas`.
3. Revisar las plantillas con peor rating y desactivarlas:
   ```sql
   UPDATE app.whatsapp_templates
   SET status = 'paused'
   WHERE tenant_id = '<tenant_id>'
     AND status = 'approved'
     AND category = 'MARKETING'
     AND id IN (SELECT id FROM app.whatsapp_templates ORDER BY quality_score ASC NULLS LAST LIMIT 3);
   ```
4. Forzar opt-out fácil en respuestas automáticas (template
   `consent_optout_v1`) durante las próximas 48 h.

## Fix definitivo

- Auditar las últimas 50 conversaciones donde se envió MARKETING: ¿el contacto
  había dado opt-in explícito (`consent_ledger.action='granted'`)? Si no,
  hay un bug en `campaign_worker` que debe corregirse.
- Reducir el `tenant_settings.campaigns.daily_marketing_cap`.
- Migrar mensajes informativos de plantilla MARKETING → UTILITY donde aplique
  (recordatorios, confirmaciones).
- Re-aprobar plantillas con copy revisado por la persona responsable de
  contenido en el tenant.

## Post-mortem checklist

- [ ] Campañas pausadas en BD.
- [ ] Plantillas problemáticas marcadas como `paused` con razón en `metadata`.
- [ ] Contar bloqueos del usuario final (`block` event en webhook) para los
      últimos 7 días.
- [ ] Documentar en `audit_logs(action='channel.quality_remediation')` qué se
      hizo y quién aprobó las medidas.
- [ ] Si `quality_rating` no vuelve a `GREEN` en 7 días → escalar a Meta
      vía Business Support con el caso completo.
