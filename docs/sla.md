# SLA — CopilotoIA

Este documento describe el SLA propuesto del producto y reporta el resultado
de la última corrida del *load test* automatizado (TASK-0072). La sección de
resultados se regenera mecánicamente desde el job `load-test` de GitHub
Actions vía `tests/load/aggregate_results.py`.

## SLA propuesto

| Indicador | Objetivo | Cómo se mide |
|---|---|---|
| Disponibilidad mensual | **99.9 %** (≤ 43 min / mes de caída no planificada) | Probe externo sobre `/v1/health` cada 60 s; ventana móvil de 30 días. |
| Latencia de respuesta | **p95 < 2.0 s, p99 < 4.0 s** sobre `/v1/webhooks/whatsapp` y endpoints del panel | Locust + métricas Prometheus (`http_request_duration_seconds`) exportadas por el API. |
| Tasa de error | **< 1 %** de 5xx sobre el total de requests durante 5 min consecutivos | Stats agregadas de Locust + alerta Prometheus `api_5xx_rate`. |
| Throughput sostenido | ≥ **50 msg/s** durante 5 min sin degradación de p95 | Job `load-test` con escenario `tests/load/test_journey_load.py`. |
| RPO (Recovery Point) | ≤ **24 h** | TASK-0064 backups automatizados + verificación cada noche. |
| RTO (Recovery Time) | ≤ **4 h** | Drill de restore documentado en TASK-0029. |

### Ventanas de mantenimiento

- Domingo 02:00–04:00 hora local del tenant principal (`America/Bogota`).
- Las ventanas se anuncian con ≥ 72 h de anticipación a la cuenta de admin
  registrada del tenant.

### Exclusiones

Quedan fuera del SLA:

- Caídas de proveedores upstream (WhatsApp Cloud API, Anthropic, OpenAI,
  Meta Webhooks). Se reportan pero no consumen *error budget*.
- Tenants en modo `paused` o con `status='inactive'`.
- Eventos de fuerza mayor (cortes de red regionales, indisponibilidad de
  la zona AWS contratada).

## Resultado del último load test

Perfil de tráfico mixto (`tests/load/test_journey_load.py`):

- **70 %** inbound `POST /v1/webhooks/whatsapp` (firma HMAC válida)
- **20 %** lecturas del panel (`GET /v1/health` + `resources/public`)
- **10 %** acciones admin via service token (`GET .../services`)

Parámetros del run de referencia: 50 usuarios, spawn 10 u/s, duración 5 min,
target host `http://localhost:8000` con el compose efímero del job
`load-test` (PostgreSQL + Redis + MinIO + API + 1 worker).

<!-- load-test-results:start -->
**Última corrida:** _pendiente — se rellena automáticamente con el primer run del job `load-test`._

- **RPS sostenido:** n/a
- **p50 / p95 / p99 (agregado):** n/a / n/a / n/a
- **Errores totales:** n/a

**Desglose por endpoint:**

| Endpoint | Reqs | Fails | RPS | p50 | p95 | p99 | avg |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — |
<!-- load-test-results:end -->

## Cómo reproducir el load test localmente

```bash
# 1. Levantar el stack completo
docker compose up -d
./scripts/bootstrap.sh

# 2. Sembrar el tenant de carga (escribe .secrets/load_test_*)
DATABASE_URL=postgresql://copiloto_app:...@localhost:5432/copilotoia \
  python -m tests.load.seed_load_tenant

# 3. Instalar Locust (sólo para el agente que corre la carga)
pip install 'locust>=2.31,<3'

# 4. Ejecutar el escenario mixto
mkdir -p tests/load/results
locust -f tests/load/test_journey_load.py \
  --host http://localhost:8000 \
  --headless --users 50 --spawn-rate 10 \
  --run-time 5m \
  --csv tests/load/results/run

# 5. Regenerar esta sección con los resultados
python -m tests.load.aggregate_results \
  --csv-prefix tests/load/results/run \
  --sla-file docs/sla.md \
  --enforce-sla
```

El script `aggregate_results.py` también es el que ejecuta el job CI; con
`--enforce-sla` retorna exit code 1 si p95 > 2000 ms o si el RPS sostenido
cae bajo el objetivo.
