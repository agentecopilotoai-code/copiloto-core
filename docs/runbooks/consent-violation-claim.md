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
-- Schema de app.consent_ledger (ver infra/postgres/01-schema.sql):
--   event        check ('granted','revoked','reaffirmed','suppressed')
--   channel      check ('whatsapp','web','admin','import')
--   evidence_payload jsonb
--   occurred_at  timestamptz
SELECT
  cl.event,
  cl.channel,
  cl.purpose,
  cl.legal_basis,
  cl.copy_shown,
  cl.evidence_payload,
  cl.occurred_at,
  cl.ip,
  cl.user_agent
FROM app.consent_ledger cl
JOIN app.contacts c ON c.tenant_id = cl.tenant_id AND c.id = cl.contact_id
WHERE c.tenant_id = '<tenant_id>'
  AND c.wa_id = '<wa_id>'
ORDER BY cl.occurred_at ASC;
```

```sql
-- 2) Mensajes enviados al contacto. messages se vincula al contact vía
--    conversations.contact_id; el cuerpo está en body_text y los flags de
--    campaña en payload (no en metadata).
SELECT
  m.id,
  m.direction,
  m.created_at,
  m.message_type,
  m.body_text,
  m.campaign_id,
  m.payload->>'template_name' AS template
FROM app.messages m
JOIN app.conversations cv ON cv.id = m.conversation_id
JOIN app.contacts c ON c.id = cv.contact_id
WHERE c.tenant_id = '<tenant_id>'
  AND c.wa_id = '<wa_id>'
ORDER BY m.created_at ASC;
```

```sql
-- 3) ¿Existió consentimiento vigente en el momento de cada envío de
--    CAMPAIGN (marketing)? Un campaign_id NOT NULL indica que el mensaje
--    fue parte de un envío masivo, no transaccional.
WITH msgs AS (
  SELECT m.id, m.created_at
  FROM app.messages m
  JOIN app.conversations cv ON cv.id = m.conversation_id
  JOIN app.contacts c ON c.id = cv.contact_id
  WHERE c.wa_id = '<wa_id>'
    AND c.tenant_id = '<tenant_id>'
    AND m.direction = 'outbound'
    AND m.campaign_id IS NOT NULL
)
SELECT
  msgs.id,
  msgs.created_at,
  (
    SELECT cl.event
    FROM app.consent_ledger cl
    JOIN app.contacts c2 ON c2.id = cl.contact_id
    WHERE c2.wa_id = '<wa_id>'
      AND c2.tenant_id = '<tenant_id>'
      AND cl.purpose = 'marketing'
      AND cl.occurred_at <= msgs.created_at
    ORDER BY cl.occurred_at DESC
    LIMIT 1
  ) AS consent_state_at_send
FROM msgs
ORDER BY msgs.created_at;
```

## Mitigación inmediata

1. **Detener envíos** al contacto inmediatamente. `app.consent_ledger` es
   append-only y exige los nombres reales de columnas (`event`,
   `evidence_payload`, `channel='admin'` para revocaciones operadas desde el
   panel; ver `infra/postgres/01-schema.sql`). Además, marcar el contacto
   como `suppressed` para que el orquestador deje de generar outbound:
   ```sql
   BEGIN;

   INSERT INTO app.consent_ledger (
     tenant_id, contact_id, event, channel, purpose,
     legal_basis, copy_shown, evidence_payload, occurred_at
   )
   SELECT
     c.tenant_id, c.id, 'revoked', 'admin', 'marketing',
     'Ley 1581 art. 8(c) - revocación a solicitud del titular',
     'Revocación registrada por el operador tras queja del titular.',
     jsonb_build_object('reason','user_complaint','ticket','<ticket_id>',
                        'operator_user_id','<operator_uuid>'),
     now()
   FROM app.contacts c
   WHERE c.tenant_id = '<tenant_id>' AND c.wa_id = '<wa_id>';

   UPDATE app.contacts
   SET opt_in_status = 'suppressed',
       opt_out_at    = now(),
       updated_at    = now()
   WHERE tenant_id = '<tenant_id>' AND wa_id = '<wa_id>';

   COMMIT;
   ```
2. Generar **extracto contact-scoped** del ledger para entregar al titular.
   ⚠️ **NO usar el endpoint `data-export` para esto.** Ese endpoint es
   tenant-wide (devuelve `tenant_settings`, channels, aggregate counts) y NO
   acepta `contact_id`/`kinds` como filtros — esos query params son
   silenciosamente ignorados por FastAPI y la response incluye datos
   internos del tenant que NUNCA se entregan a un complainant externo. Ver
   finding Codex `6317cdc8` / SEC-010 sub-ticket.

   Mientras existe un endpoint contact-scoped (ver follow-up
   `SEC-010-EXPORT-FU` más abajo), el operador debe componer manualmente el
   extracto vía SQL — solo las tablas que tocan al contacto:
   ```sql
   -- Consent ledger del contacto (filtra por wa_id y tenant_id)
   SELECT created_at, event_type, channel, metadata
   FROM   app.consent_ledger
   WHERE  tenant_id = '<tenant_id>' AND wa_id = '<wa_id>'
   ORDER  BY created_at ASC;

   -- Mensajes del contacto (solo el wa_id reclamante)
   SELECT created_at, direction, channel, body
   FROM   app.messages
   WHERE  tenant_id = '<tenant_id>' AND wa_id = '<wa_id>'
   ORDER  BY created_at ASC;
   ```
   Exportar a JSON/CSV firmado con `pg_dump --data-only --table=...` o vía
   un script ad-hoc que el operador audita antes de entregar.

   **Follow-up declarado:** `SEC-010-EXPORT-FU` — agregar
   `GET /v1/tenants/{tenant_id}/contacts/{contact_id}/export?kinds=...` con
   capability dedicada (`contact.export.read`), audit log
   `contact.exported_for_consent_claim`, y firma del archivo de salida.
   Hasta entonces el operador es responsable de la redacción.
3. Si la queja es por canal masivo (campaña): identificar la campaña vía
   `messages.campaign_id` (query #2) y cancelarla si más de un caso reporta
   lo mismo:
   ```sql
   UPDATE app.campaigns
   SET status = 'cancelled', updated_at = now()
   WHERE id = '<campaign_id>' AND status = 'running';
   ```
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
