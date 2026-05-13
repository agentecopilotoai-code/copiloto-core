# Runbook — Circuit breaker abierto sostenidamente

## Síntoma

- Alerta `CircuitBreakerOpenSustained`:
  `cpi_circuit_breaker_state{provider="<...>"} >= 2` durante >2 min.
- El `provider` puede ser `meta_graph`, `cloud_llm:claude`,
  `cloud_llm:openai`, `stripe`, `mercadopago` u `ollama`.
- Mensajes outbound o respuestas del bot bloqueadas; en logs aparece
  `CircuitBreakerOpenError`.

## Diagnóstico

```bash
# 1) Listado de breakers y su estado actual.
curl -sS http://localhost:8000/metrics | grep cpi_circuit_breaker_state

# 2) Histograma de fallos por provider (últimos 15 min).
curl -sS "http://localhost:8000/metrics" | grep -E 'cpi_provider_call_total'
```

```sql
-- Errores recientes (el provider downstream solo se distingue por el rango
-- del error_code: códigos de Meta son numéricos 4–6 dígitos; transport_error
-- agrupa fallos de red; http_4xx/5xx vienen de proveedores externos).
SELECT
  COALESCE(NULLIF(error_code, ''), 'transport_error') AS code,
  LEFT(COALESCE(error_message, ''), 120) AS sample_message,
  COUNT(*) AS occurrences,
  MAX(created_at) AS last_seen
FROM app.messages
WHERE created_at > now() - interval '30 minutes'
  AND status = 'failed'
GROUP BY 1, 2
ORDER BY occurrences DESC;
```

## Mitigación inmediata

Depende del `provider`:

- `meta_graph` → ver [meta-token-expired.md](meta-token-expired.md) y
  [rate-limit-meta-hit.md](rate-limit-meta-hit.md).
- `cloud_llm:*` → ver [cloud-llm-rate-limited.md](cloud-llm-rate-limited.md).
- `stripe` / `mercadopago` → revisar status page del proveedor; pausar
  generación de links de pago (`UPDATE app.tenant_settings
  SET payments_enabled = false WHERE ...`) hasta que recupere.
- `ollama` → reiniciar contenedor: `docker compose restart ollama`. Verificar
  RAM disponible (Ollama necesita ≥4GB libres para llama3.2:3b).

**Forzar reseteo manual** del breaker tras corregir la causa raíz:

```bash
curl -sS -X POST http://localhost:8000/internal/circuit-breakers/<provider>/reset \
  -H "X-Internal-Token: ${INTERNAL_ADMIN_TOKEN}"
```

## Fix definitivo

- Validar que los umbrales del breaker (5 fallos consecutivos / 30s) son
  apropiados para cada provider. Stripe puede tolerar más; Meta no.
- Implementar **fallback automático** provider-to-provider cuando exista
  alternativa (anthropic ↔ openai, stripe ↔ mercadopago).
- Añadir alerta de **proximidad** (`cpi_circuit_breaker_state == 1`) que
  avise antes de la apertura completa.

## Post-mortem checklist

- [ ] Causa raíz por provider documentada.
- [ ] Breaker volvió a `closed` (state=0) y se mantiene estable.
- [ ] Sí/no se hizo failover; documentar la decisión.
- [ ] Si fue cuota/billing: incrementar plan o reservar capacidad.
