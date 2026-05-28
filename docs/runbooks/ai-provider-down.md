# Runbook — AI provider down

**Alerta:** `AiProviderDown` (severity: ticket)
**Trigger:** `cpi_ai_provider_health{provider=X,modality=Y} == 0` por > 5 min
**Categoría:** Operaciones / AI

---

## Síntoma

- Alerta dispara con label `provider` + `modality` específicos.
- Logs muestran `ProviderUnavailable`, `ProviderTimeoutError` o
  `ProviderRateLimited` repetidos para ese provider.
- Si hay fallback chain configurado, las requests SIGUEN funcionando
  pero con costo/latencia/calidad degradada.

## Diagnóstico

1. **Verificar status del provider externo:**
   - OpenAI: https://status.openai.com
   - Anthropic: https://status.anthropic.com
   - xAI (Grok): https://status.x.ai
   - ElevenLabs: https://status.elevenlabs.io
   - Ollama / local_sdxl / local_whisper: container local — `docker ps`.

2. **Verificar logs del worker:**

   ```bash
   kubectl logs -l app=copilotoia-api --tail=200 \
     | grep -iE "provider.*$PROVIDER.*(unavailable|timeout|rate_limited)"
   ```

3. **Verificar el circuit breaker:**

   El gauge `cpi_ai_provider_health == 0` solo refleja el breaker abierto.
   El breaker se abre tras 5 fallos en 60s y cierra cooldown=300s.

4. **¿API key válida?**

   ```bash
   # Buscar last 401 contra el provider.
   kubectl logs -l app=copilotoia-api --tail=500 \
     | grep -i "401" | grep -i "$PROVIDER"
   ```

5. **¿Quota agotada?**

   Revisar el dashboard del provider. Para OpenAI/Anthropic, la
   quota mensual se ve en sus consolas.

## Mitigación

### Caso A — Provider caído upstream

- **Notificar al provider** si no hay status público.
- **Confirmar fallback chain funciona:** revisar `cpi_ai_dispatch_audits`
  table (si existe) o métrica `cpi_provider_fallback_used_total`.
- **No tomar acción más** — el breaker cierra solo cuando el provider
  responda OK.

### Caso B — Key inválida / rotada sin propagar

```bash
# Verificar que el secret está montado en el pod
kubectl exec deployment/copilotoia-api -- env | grep -i "$PROVIDER"

# Si la key está vacía o stale, actualizar el secret en el store
kubectl create secret generic ai-keys-new \
  --from-literal=openai_api_key='<NEW_KEY>' -n copilotoia

# Rolling restart con el nuevo secret
kubectl set env deployment/copilotoia-api \
  --from=secret/ai-keys-new
kubectl rollout status deployment/copilotoia-api
```

### Caso C — Quota agotada

- Upgrade del plan del provider.
- Mientras tanto: forzar fallback agresivo desactivando el primary:

  ```bash
  # Vía /admin/api/v1/platform/ai-providers PATCH
  curl -X PATCH https://api.copilotoia.com/v1/platform/ai-providers/$PROVIDER_ID \
    -H "Authorization: Bearer $ADMIN_JWT" \
    -d '{"enabled": false, "reason": "quota_exhausted"}'
  ```

### Caso D — Local provider (ollama/sdxl/whisper) caído

```bash
# Verificar container
docker ps -f name=ollama
docker logs ollama --tail=50

# Restart si está stuck
docker restart ollama

# Health check directo
curl http://localhost:11434/api/tags
```

## Verificación

- `cpi_ai_provider_health{provider=X} == 1` por 5+ min.
- 0 nuevos `ProviderUnavailable` para ese provider en los últimos 5 min.

## Cuándo escalar

- Si el provider está caído > 1 hora y el fallback es local
  (latencia/calidad notablemente peor) → notificar a product.
- Si NO hay fallback configurado para esa modality → escalar a P1.

## Última revisión

2026-05-27 — TASK-PROD post audit#4.
