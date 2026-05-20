# Runbook — Generación atascada en `queued` o `running`

**TASK-INFLU-018 — Observabilidad del módulo Ravit Studio.**

## Síntomas

- Tenant reporta que una generación "no avanza" tras > 5 min.
- Alert `InfluencerGenerationP95High` disparada (p95 duration > 60s en
  ventana 10min).
- Query: `select * from influencer.generations where status='running' and started_at < now() - interval '5 min'`.

## Triage rápido

1. **¿Cuál provider está fallando?**
   ```sql
   select provider_primary, count(*) as fail_count
   from influencer.provider_dispatch
   where occurred_at > now() - interval '10 min' and success = false
   group by provider_primary order by fail_count desc;
   ```
2. **¿Hay circuit breaker abierto?** Revisar logs del worker:
   `circuit breaker opened for provider <name>`.
3. **¿El provider devolvió `content_rejected`?** Mirar
   `influencer.generations.error_message='content_rejected'`. Si sí, NO
   reintentar — el filter rechazaría otra vez. Refund automático ya
   ejecutado por TASK-INFLU-016.

## Mitigación

- **Provider down:** verificar `influencer_provider_health{provider}`
  metric. Si está en 0 por >5min, cambiar el provider primario vía
  `PATCH /v1/platform/ai-providers/{modality}` con un `provider` del
  fallback chain.
- **Hung job:** marcar `status='failed'` con `error_message='runbook-manual-cancel'`
  y reembolsar créditos vía `credit(..., reason='refund:stuck:{gen_id}')`.

## Postmortem

Cualquier generación que tarde > 5 min debe generar un PR de fix con:
- Origen del retraso (provider lento? worker overloaded? content filter no documentado?).
- Update del runbook si la causa raíz no estaba cubierta aquí.
