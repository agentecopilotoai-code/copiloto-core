# Arquitectura — Copiloto Core

Branch **core**: solo el sistema operativo transversal. Sin productos
(chatbot/whatsapp/gd/influencer fueron purgados durante la limpieza
del branch — ver `git log` de M1-M10 para el detalle).

## Componentes

```
┌────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│    └─→ http://localhost:3000  → Admin Panel (BFF)                  │
│         OAuth callback Auth0 → cookie de sesión HMAC-firmada       │
└──────────────────┬─────────────────────────────────────────────────┘
                   │ Bearer + X-Tenant-Id + X-Admin-User-Email
                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  API core (http://localhost:8000)                                  │
│    ├─ /v1/health                          (público)                │
│    ├─ /v1/me/*                            (auth JWT)               │
│    ├─ /v1/tenant-signup                   (auth JWT, sin tenant)   │
│    ├─ /v1/me/tenants                      (auth JWT)               │
│    ├─ /v1/tenants/*                       (platform_owner + MFA)   │
│    ├─ /v1/platform/*                      (platform_owner + MFA)   │
│    └─ /metrics                            (IP allowlist)           │
└──────────────────┬─────────────────────────────────────────────────┘
                   │ asyncpg (RLS por tenant_id + support_mode)
                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  PostgreSQL 16 + pgvector                                          │
│    ├─ schema `app`: tenants, users, user_tenant_roles,             │
│    │                user_preferences, auth_sessions, audit_logs,   │
│    │                operator_alerts, backup_runs, tenant_modules,  │
│    │                platform_secrets, platform_ai_providers,       │
│    │                provider_dispatch, feature_flags,              │
│    │                role, capability, role_capability              │
│    └─ Row-Level Security en todas las tablas tenant-scoped.        │
└────────────────────────────────────────────────────────────────────┘
```

## Cómo agregar un módulo nuevo

Un "módulo opt-in" es un producto (chatbot, gd, influencer, etc.) que
se instala SOBRE el core sin tocar su código. Cada módulo aporta:

1. **Schema SQL** en `infra/postgres/modules/<name>.sql`.
   - `CREATE SCHEMA IF NOT EXISTS <name>;`
   - Tablas tenant-scoped con RLS habilitada.
   - Seed de catálogos (roles del módulo, permisos, etc.).
   - Idempotente (todo con `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`).

2. **Handlers FastAPI** registrados con su propio router
   (`@my_module_router.get('/v1/<name>/...')`).

3. **Activación per-tenant** via `app.tenant_modules` (el
   `platform_owner` activa/desactiva con
   `PATCH /v1/platform/tenant-modules/{tid}/{module}`).

4. **Bootstrap específico** opcional: si el módulo necesita seed
   adicional por tenant cuando se activa, registrarlo en su propio
   handler de activación (`tenant_modules` PATCH trigger).

5. **Tests + cobertura ≥95%** consistente con el gate del CI.

El core NO conoce módulos específicos por diseño. El CHECK constraint
de `app.tenant_modules.module` acepta cualquier string — la validación
de nombre canónico la hace cada módulo en su bootstrap.

## Capabilities & roles

- `app.role` seed: `platform_owner, owner, admin, manager, agent,
  viewer` (sin `support` — la suplantación cross-tenant se modela vía
  cookie `support_mode` con TTL, no como rol).
- `app.capability` seed: solo capacidades del core (tenant_setup.*,
  team.*, platform.*). Los módulos opt-in agregan las suyas (por
  ejemplo `chatbot.messages.write`).
- `app.role_capability` mapea quién puede qué. El frontend espeja la
  matriz en `admin-panel/src/permissions/matrix.js`.

## Soporte cross-tenant (support_mode)

El `platform_owner` no aparece en `user_tenant_roles` por diseño. Para
operar dentro de un tenant ajeno:

1. `POST /v1/me/support-mode/{tenant_id}` con `justification` (≥8
   chars) → cookie HMAC-firmada `copilotoia_support_mode` con TTL 1h.
2. Cada request al core que incluya `X-Tenant-Id` matching la cookie
   activa `app.support_mode='true'` en la transacción → RLS permite
   el acceso cross-tenant.
3. `DELETE /v1/me/support-mode/{tenant_id}` o expiración del cookie
   → vuelve al gate normal.

Toda activación/desactivación queda en `audit_logs` con
`metadata.justification_provided` y `metadata.roles`.

## Observability

- **`/metrics`** (Prometheus): IP allowlist (`OBSERVABILITY_ALLOWED_IPS`).
  Gauges activos: `cpi_ws_fanout_*`, `cpi_rate_limit_*`,
  `cpi_backup_last_*`, `cpi_ai_provider_health`.
- **`infra/observability/alerts.yaml`**: solo alertas con métrica viva
  (BackupCloudStale, BackupVerifyFailed, MetricsEndpointSilent). Las
  de módulos opt-in (chatbot, workers, circuit breaker) se removieron;
  cada módulo re-introduce las suyas al instalarse.
- **OpenTelemetry**: el collector está cableado en docker-compose pero
  el app NO emite traces. Cuando se necesite, instrumentar con
  `opentelemetry-instrumentation-fastapi`.

## Seguridad — defensa en profundidad

| Capa | Defensa |
|---|---|
| Network | Reverse proxy delante (nginx/ALB) + `TRUST_PROXY_FORWARDED_FOR=true` opcional |
| Headers | CSP, X-Frame-Options=DENY, HSTS, Referrer-Policy=no-referrer |
| Auth | Auth0 RS256 + JWKS cache + MFA enforcement para roles privilegiados |
| BFF | CSRF (Sec-Fetch-Site + X-Requested-With), cookies HMAC-firmadas |
| API | RLS Postgres + `app.tenant_id` + `app.support_mode` por transacción |
| Schemas | Pydantic `extra='forbid'` + slug pattern + tipos estrictos |
| Audit | `audit_logs` append-only (UPDATE/DELETE bloqueados por policy) |

## Tests + CI

- **Backend**: ≥95% coverage (gate en `.github/workflows/ci.yml`).
  Tests unit en `tests/test_unit_*.py` usan FakeConn + handler-direct
  para no requerir Postgres real.
- **Frontend**: 98.6% coverage (gate en `admin-panel/vitest.config.js`).
- **E2E**: `pytest -m e2e` requiere Postgres ephemeral del CI (job
  `coverage-gate`).
- **Local fast loop**: `./scripts/ci-local-fast.sh` (lint + unit, ~30s).
- **Local full**: `./scripts/ci-local-full.sh` (todo + coverage gate).
