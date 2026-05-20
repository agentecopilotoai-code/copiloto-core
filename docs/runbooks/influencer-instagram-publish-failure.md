# Runbook — Falla de publicación en Instagram

**TASK-INFLU-018 — Observabilidad del módulo Ravit Studio.**

## Síntomas

- Alert `InfluencerPublishFailures` (`rate(influencer_posts_published_total{status='failed'}[15m]) > 0.1`).
- Tenant reporta posts no aparecen en su feed.

## Triage

1. **¿Token expirado?**
   ```sql
   select persona_id, status, expires_at
   from influencer.platform_connections
   where platform='instagram' and expires_at < now();
   ```
   Si sí → status pasa a `'expired'`; UI muestra "Reconectar Instagram"
   y dispara `/oauth/start` flow nuevamente.

2. **¿Rate limit?** Instagram Graph API: 200 calls/hr per user. Si el
   error contiene `rate_limited`, hacer backoff exponencial (el
   `publish_worker` debe hacerlo automáticamente; verificar que
   `publish` factory cubre este caso).

3. **¿Content rejection por Meta?** Si el caption viola las community
   guidelines, Meta rechaza. Mirar `posts.error_message` y mostrar al
   tenant para que edite caption.

## Mitigación inmediata

- Reagendar el post: `PATCH /v1/influencer/posts/{id}` con un nuevo
  `scheduled_at` o `status='canceled'` si no aplica.
- Si el token está expirado, NO retry automático — fuerza reconexión
  manual (security: tenant debe re-autorizar el scope).
