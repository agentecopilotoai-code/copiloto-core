# Runbook — Flood de webhooks (rate_limit.blocked >100/min)

## Síntoma

- Pico de respuestas HTTP 429 en
  `/v1/webhooks/meta` (visible en logs y métrica
  `cpi_rate_limit_blocked_total >100/min`).
- Crecimiento atípico de `tenant_id=NULL` o `tenant_id=desconocido` en
  `audit_logs(action='webhook.rejected')`.
- Inbound desproporcionado vs ventana habitual.

## Diagnóstico

```bash
# Rate de rechazos por IP en la última hora.
docker compose logs --tail=5000 api 2>/dev/null \
  | grep "webhook.rejected" \
  | awk '{print $NF}' | sort | uniq -c | sort -rn | head -20
```

```sql
-- ¿Qué tenant_channel está siendo atacado o tiene config errónea?
SELECT
  COALESCE(metadata->>'channel_id', '<sin canal>') AS channel,
  COALESCE(metadata->>'remote_ip', '<sin ip>') AS ip,
  COUNT(*) AS hits
FROM app.audit_logs
WHERE action IN ('webhook.rejected', 'webhook.signature_invalid')
  AND created_at > now() - interval '30 minutes'
GROUP BY 1, 2
ORDER BY hits DESC
LIMIT 20;
```

```sql
-- Confirmar si la firma HMAC viene incorrecta (sospechoso = bot externo).
SELECT
  metadata->>'reason' AS reason,
  COUNT(*) AS occurrences
FROM app.audit_logs
WHERE action = 'webhook.signature_invalid'
  AND created_at > now() - interval '15 minutes'
GROUP BY 1;
```

## Mitigación inmediata

1. **Confirmar legitimidad:** todo webhook Meta válido tiene firma HMAC
   válida (`X-Hub-Signature-256`). Si las firmas son inválidas → es tráfico
   externo malicioso. Bloquear a nivel de red:
   ```bash
   # Ejemplo con iptables/host firewall del cluster.
   sudo iptables -A INPUT -s <IP_ATACANTE> -j DROP
   ```
   En producción usar el WAF del balanceador (CloudFront, Cloudflare,
   AWS WAF) y aplicar regla de rate-limit por IP.
2. **Subir el rate limit interno** para tráfico legítimo (si Meta hace burst
   real tras downtime):
   ```bash
   docker compose exec api \
     python -m app.tools.set_runtime_config \
       --key rate_limit.webhook.requests_per_minute --value 600
   ```
3. Verificar que el `tenant_channels.signing_secret` no se filtró: si el
   ataque viene con firmas válidas, **rotar el secret** desde Meta App
   Settings y actualizar el canal.
4. Si Postgres está sufriendo por escrituras en `audit_logs`, deshabilitar
   temporalmente el logging detallado de webhooks rechazados.

## Fix definitivo

- WAF con rate-limit por IP frente a `/v1/webhooks/*` (10 rps por IP en
  baseline).
- Validar firma HMAC **antes** de hacer cualquier I/O o lookup en BD para
  reducir costo del rechazo.
- Bloquear ASN/regiones no esperadas para webhooks de Meta (Meta publica los
  rangos oficiales).
- Alerta proactiva: `cpi_rate_limit_blocked_total > 50/min` durante 1 min
  (regla pendiente — owner: plataforma).

## Post-mortem checklist

- [ ] Origen identificado (ASN, IP, hipótesis).
- [ ] Reglas de WAF actualizadas y versionadas.
- [ ] Rotación de secretos si hubo sospecha de leak.
- [ ] Sin impacto a tenants legítimos confirmado (`messages.created_at`
      continuo durante el flood).
- [ ] Reporte abuso al ASN si aplica.
