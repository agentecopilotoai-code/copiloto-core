# Runbook — Queja por violación de consentimiento (Ley 1581 / GDPR)

## Síntoma

- Queja del cliente final por escrito (email, WhatsApp, formulario) alegando
  que recibió mensajes sin haber otorgado consentimiento.
- Solicitud formal de la **SIC** (Superintendencia de Industria y Comercio)
  o del titular ejerciendo *derecho de supresión* / *habeas data*.
- Notificación interna del manager del tenant tras revisión rutinaria del
  consent dashboard.

## Diagnóstico

```sql
-- 1) Historial completo del consentimiento del contacto.
SELECT
  cl.action,           -- granted | revoked | renewed
  cl.channel,          -- whatsapp | web | manual
  cl.purpose,          -- transactional | marketing | analytics
  cl.evidence,         -- jsonb: ip, user_agent, message_id, etc.
  cl.created_at,
  cl.actor_id
FROM app.consent_ledger cl
JOIN app.contacts c ON c.tenant_id = cl.tenant_id AND c.id = cl.contact_id
WHERE c.tenant_id = '<tenant_id>'
  AND (c.wa_id = '<wa_id>' OR c.email = '<email>')
ORDER BY cl.created_at ASC;
```

```sql
-- 2) Mensajes enviados al contacto, junto con su clasificación
--    (transactional / marketing / campaign).
SELECT
  m.id,
  m.direction,
  m.created_at,
  m.body,
  m.metadata->>'category' AS category,
  m.metadata->>'campaign_id' AS campaign_id,
  m.metadata->>'template_name' AS template
FROM app.messages m
JOIN app.contacts c ON c.tenant_id = m.tenant_id AND c.id = m.contact_id
WHERE c.tenant_id = '<tenant_id>'
  AND c.wa_id = '<wa_id>'
ORDER BY m.created_at ASC;
```

```sql
-- 3) ¿Existió consentimiento vigente en el momento de cada envío MARKETING?
WITH msgs AS (
  SELECT m.id, m.created_at
  FROM app.messages m
  JOIN app.contacts c ON c.id = m.contact_id
  WHERE c.wa_id = '<wa_id>'
    AND m.direction='outbound'
    AND (m.metadata->>'category') = 'marketing'
)
SELECT
  msgs.id,
  msgs.created_at,
  (
    SELECT cl.action
    FROM app.consent_ledger cl
    WHERE cl.contact_id = (SELECT id FROM app.contacts WHERE wa_id='<wa_id>')
      AND cl.purpose = 'marketing'
      AND cl.created_at <= msgs.created_at
    ORDER BY cl.created_at DESC LIMIT 1
  ) AS consent_state_at_send
FROM msgs
ORDER BY msgs.created_at;
```

## Mitigación inmediata

1. **Detener envíos** al contacto inmediatamente:
   ```sql
   INSERT INTO app.consent_ledger (tenant_id, contact_id, action, purpose, channel, evidence)
   SELECT tenant_id, id, 'revoked', 'all', 'manual',
          jsonb_build_object('reason','user_complaint','ticket','<id>')
   FROM app.contacts WHERE wa_id = '<wa_id>' AND tenant_id = '<tenant_id>';
   ```
2. Generar **extracto del ledger** para entregar al titular:
   ```bash
   docker compose exec api \
     python -m app.tools.consent_export \
       --tenant <id> --contact <wa_id_or_email> \
       --output ./extracto-<wa_id>.pdf
   ```
3. Si la queja es por canal masivo (campaña): revisar las últimas 24h de la
   campaña y pausarla si más de un caso reportó lo mismo.
4. Responder al titular dentro del plazo legal (15 días hábiles en Colombia
   bajo Ley 1581) con el extracto firmado y la confirmación de supresión.

## Fix definitivo

- Revisar el flujo que persistió el consentimiento original. Si fue un opt-in
  débil (asumido tras inbound sin doble confirmación), corregir
  `consent_flow.py` para exigir doble opt-in (TASK-0062 ya lo cubre).
- Auditar `campaign_worker.send_eligible`: nunca debe enviar marketing si el
  último estado del `consent_ledger` para `purpose='marketing'` no es
  `granted` o `renewed`.
- Reforzar tests `test_consent_ledger_static.py` con el caso reportado.
- Si la queja escaló a la SIC: archivar el caso en `docs/sic-incidents/` y
  cumplir las medidas correctivas pedidas.

## Post-mortem checklist

- [ ] Extracto del ledger entregado al titular dentro del plazo.
- [ ] Supresión confirmada (no hay más outbound al contacto).
- [ ] Causa raíz del envío indebido documentada.
- [ ] Si fue un bug en `campaign_worker`: PR con fix + test que reproduce.
- [ ] DPO notificado y registro del caso en el inventario de incidentes
      privacidad.
- [ ] Si afectó >1 contacto: notificación masiva a los afectados con el mismo
      extracto.
