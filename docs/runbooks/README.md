# Runbooks operacionales — CopilotoIA

Esta carpeta contiene un runbook por tipo de incidente. Cada runbook sigue el
mismo formato:

1. **Síntoma** — qué se observa (alerta de Prometheus, queja, métrica, log).
2. **Diagnóstico** — comandos concretos (SQL, curl, `docker compose`) para
   confirmar la causa.
3. **Mitigación inmediata** — pasos que reducen el impacto en < 15 min.
4. **Fix definitivo** — solución estructural que evita la recurrencia.
5. **Post-mortem checklist** — qué archivar tras el incidente.

Cada regla de alerta en `infra/observability/alerts.yaml` apunta al runbook
correspondiente vía la anotación `runbook_url`. El test estático
`tests/test_runbooks_static.py` verifica que todos los `runbook_url`
referenciados existan en este directorio.

## Índice

| Runbook | Alerta asociada |
|---------|-----------------|
| [meta-token-expired.md](meta-token-expired.md) | `OutboundDLQGrowing` (error 190) |
| [meta-quality-rating-dropped.md](meta-quality-rating-dropped.md) | (manual) `tenant_channels.quality_rating='RED'` |
| [postgres-down.md](postgres-down.md) | `BotResponseLatencyP95High` sostenida + healthcheck rojo |
| [rate-limit-meta-hit.md](rate-limit-meta-hit.md) | `HighOutboundErrorRate` (error 80007) |
| [cloud-llm-rate-limited.md](cloud-llm-rate-limited.md) | `CircuitBreakerOpenSustained` (provider claude/openai) |
| [circuit-breaker-open-sustained.md](circuit-breaker-open-sustained.md) | `CircuitBreakerOpenSustained` |
| [worker-queue-backlog.md](worker-queue-backlog.md) | `WorkerQueueBacklog`, `SchedulerBehind` |
| [webhook-flood.md](webhook-flood.md) | (manual) ráfaga 429 en `rate_limit.blocked` |
| [consent-violation-claim.md](consent-violation-claim.md) | (manual) queja del cliente / SIC |

Los runbooks de backup viven en `docs/backup-policy.md` y están enlazados desde
las alertas `BackupCloudStale` y `BackupVerifyFailed`.
