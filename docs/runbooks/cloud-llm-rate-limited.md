# Runbook — Cloud LLM rate-limited o caído (Claude / OpenAI)

## Síntoma

- Alerta `CircuitBreakerOpenSustained` con
  `provider="cloud_llm:claude"` o `provider="cloud_llm:openai"`.
- Latencia P95 alta en `BotResponseLatencyP95High` por timeouts del LLM.
- Logs del API con `anthropic.RateLimitError` u `openai.RateLimitError`.
- Métricas `cpi_llm_request_total{status="rate_limited"}` creciendo.

## Diagnóstico

```bash
# Estado del circuit breaker.
curl -sS http://localhost:8000/metrics | grep cpi_circuit_breaker_state

# Últimos errores del provider.
docker compose logs --tail=200 api | grep -E "RateLimitError|429|circuit_breaker"
```

```sql
-- Volumen de outbound bot en la última hora por tenant (el engine usado
-- queda en payload.answer_engine cuando rag_orchestrator persiste la respuesta).
SELECT
  m.tenant_id,
  COUNT(*) FILTER (WHERE m.payload->>'answer_engine' = 'cloud_llm') AS cloud_calls,
  COUNT(*) FILTER (WHERE m.status = 'failed') AS failed
FROM app.messages m
WHERE m.direction = 'outbound'
  AND m.sender_actor_type = 'bot'
  AND m.created_at > now() - interval '1 hour'
GROUP BY m.tenant_id
ORDER BY cloud_calls DESC;
```

> **Importante:** `answer_engine` y `cloud_llm_provider` son **settings
> globales** (env vars consumidas por `app/core/config.py`), no columnas de
> `app.tenant_settings`. La mitigación inmediata aplica a *todos* los
> tenants. No existe degradación por-tenant en el MVP; cuando se necesite,
> ver la sección "Fix definitivo".

## Mitigación inmediata

1. **Degradar globalmente a `cascade`** (template → Ollama → cloud) o a
   `local_llm` (solo Ollama). Esto se hace cambiando la env var
   `ANSWER_ENGINE` y reiniciando `api` + `event-worker`:
   ```bash
   # Edita .env (o el bloque environment del docker-compose.yml):
   #   ANSWER_ENGINE=cascade        # mantiene cloud como tier-3, prioriza Ollama
   #   ANSWER_ENGINE=local_llm      # ignora cloud completamente
   docker compose up -d --no-deps --force-recreate api event-worker
   ```
   El motor `cascade` ya prueba template → Ollama → cloud; degradar a
   `local_llm` evita por completo el provider rate-limited.
2. Verificar que el contenedor `ollama` está sano antes de degradar:
   ```bash
   docker compose ps ollama
   curl -sS http://localhost:11434/api/tags
   ```
3. **Cambiar el provider cloud** (Anthropic ↔ OpenAI) si solo uno está
   rate-limited y el cascade sigue siendo deseable. También es env var:
   ```bash
   # CLOUD_LLM_PROVIDER=openai  (era 'claude'), o viceversa
   # CLOUD_LLM_API_KEY=<key del provider alterno>
   # CLOUD_LLM_MODEL=<modelo>
   docker compose up -d --no-deps --force-recreate api event-worker
   ```
4. Si el rate es organizacional (cuota Anthropic/OpenAI agotada), abrir
   ticket de billing y subir el límite del workspace.

## Fix definitivo

- **Llevar `answer_engine` y `cloud_llm_provider` a `app.tenant_settings`**
  (columnas dedicadas + override por tenant) para poder degradar tenant a
  tenant en lugar de globalmente. Hoy es env-var-only.
- Implementar **rate limit por tenant** en `cloud_llm_client` (token bucket
  por `tenant_id`) para impedir que un tenant ruidoso queme la cuota global.
- Cache de respuestas frecuentes vía `rag_orchestrator.response_cache`
  con TTL corto (60s) para preguntas repetidas.
- Comprar plan con mayor cuota o reservar capacidad provisionada para los
  picos.
- Alerta proactiva en `cpi_llm_request_total{status="rate_limited"} > 0`
  durante 1 min para reaccionar antes que el breaker abra.

## Post-mortem checklist

- [ ] Restaurar `ANSWER_ENGINE` y `CLOUD_LLM_PROVIDER` originales tras la
      degradación.
- [ ] Cerrar el circuit breaker (auto-cierra tras window de éxito, verificar).
- [ ] Documentar el pico (RPM observado vs cuota del workspace).
- [ ] Si la degradación a Ollama fue notoria en calidad: comunicar al cliente.
