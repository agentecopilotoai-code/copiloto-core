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
-- Volumen de requests cloud LLM por tenant en la última hora.
SELECT
  tenant_id,
  COUNT(*) FILTER (WHERE metadata->>'engine' = 'cloud_llm') AS cloud_calls,
  COUNT(*) FILTER (WHERE metadata->>'engine_error' IS NOT NULL) AS errors
FROM app.messages
WHERE direction = 'outbound'
  AND created_at > now() - interval '1 hour'
GROUP BY tenant_id
ORDER BY cloud_calls DESC;
```

## Mitigación inmediata

1. **Degradar a `answer_engine='local_llm'`** para los tenants con tráfico
   alto:
   ```sql
   UPDATE app.tenant_settings
   SET answer_engine = 'local_llm', updated_at = now()
   WHERE tenant_id IN (
     SELECT tenant_id FROM app.messages
     WHERE direction='outbound' AND created_at > now() - interval '1 hour'
     GROUP BY tenant_id ORDER BY COUNT(*) DESC LIMIT 5
   );
   ```
   El motor `cascade` ya prueba template → Ollama → cloud, así que cambiar a
   `local_llm` mantiene el servicio aunque con respuestas menos sofisticadas.
2. Verificar que el contenedor `ollama` está sano (`docker compose ps ollama`,
   `curl -sS http://localhost:11434/api/tags`).
3. Para tenants premium con SLA estricto, **cambiar el provider** dentro de
   cloud_llm:
   ```sql
   UPDATE app.tenant_settings
   SET cloud_llm_provider = 'openai'
   WHERE tenant_id = '<tenant_id>' AND cloud_llm_provider = 'anthropic';
   ```
   (o viceversa).
4. Si el rate es organizacional (cuota Anthropic/OpenAI agotada), abrir
   ticket de billing y subir el límite del workspace.

## Fix definitivo

- Implementar **rate limit por tenant** en `cloud_llm_client` (token bucket
  por `tenant_id`) para impedir que un tenant ruidoso queme la cuota global.
- Cache de respuestas frecuentes vía `rag_orchestrator.response_cache`
  con TTL corto (60s) para preguntas repetidas.
- Comprar plan con mayor cuota o reservar capacidad provisionada para los
  picos.
- Alerta proactiva en `cpi_llm_request_total{status="rate_limited"} > 0`
  durante 1 min para reaccionar antes que el breaker abra.

## Post-mortem checklist

- [ ] Restaurar `answer_engine` original para los tenants degradados.
- [ ] Cerrar el circuit breaker (auto-cierra tras window de éxito, verificar).
- [ ] Documentar el pico (RPM observado vs cuota del workspace).
- [ ] Si la degradación a Ollama fue notoria en calidad: comunicar al cliente.
