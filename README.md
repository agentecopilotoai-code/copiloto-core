# Copiloto Core

> **Sistema operativo multi-tenant para construir SaaS de productos verticales.**

Copiloto Core es la base sobre la cual cualquier producto SaaS multi-tenant
se construye: autenticación con Auth0 + MFA, gestión de tenants, control
de membresía, configuración cross-modal de proveedores IA, runbooks,
incidentes, monitor de salud, billing & MRR, feature flags, matriz de
roles & permisos. **El core nunca conoce productos** — los módulos opt-in
se instalan encima sin modificarlo.

## ¿Qué incluye el core?

### Backend (`app/`)
- **`app/core/`** — auth, identity, config, logging. Transversal.
- **`app/db/`** — pool asyncpg + helpers RLS multi-tenant.
- **`app/ai/`** — registry + dispatcher de proveedores LLM/Image/Video/TTS/STT.
- **`app/admin/`** — BFF del admin-panel (Auth0 + session cookies +
  proxy a la Core API).
- **`app/platform_admin/`** — endpoints platform-owner-only
  (`/v1/platform/ai-providers/*`, `/v1/platform/tenant-modules/*`).
- **`app/api/v1/handlers/`** — endpoints transversales: `public`,
  `me`, `tenant_signup`, `tenant_user`, `platform_admin`, `platform_roles`.
- **`app/services/`** — utilidades transversales: audit, metrics,
  rate_limit, legal, locale, secret_resolver.

### Frontend (`admin-panel/`)
- **Platform admin** completo: Fleet, System Health, Billing & MRR,
  Incidents, Outbound DLQ, Runbooks, Roles & ACL, Feature flags,
  Proveedores IA.
- **Tenant transversales**: Configuración del tenant, Equipo.
- **"Mi cuenta"**: perfil, preferencias, notificaciones, sesiones.

### Infraestructura (`infra/postgres/`)
- **`10-core.sql`** — schema `app.*` con RLS, tenant_modules,
  platform_ai_providers, provider_dispatch (audit IA), feature_flags,
  audit_logs, roles & capabilities.
- **`20-seed.sql`** — tenant demo mínimo para dev local.

## ¿Cómo se instala un módulo opt-in sobre el core?

Cada módulo vive en su propio paquete (`app/<modulo>/`) y subdirectorio
de features (`admin-panel/src/features/<modulo>/`), con su SQL aislado
en `infra/postgres/modules/<modulo>.sql`. La activación es por tenant:
una fila en `app.tenant_modules (tenant_id, module, enabled)`.

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) § "Cómo agregar un
módulo nuevo (checklist)".

## Quick start

```bash
git clone https://github.com/agentecopilotoai-code/copiloto-core.git
cd copiloto-core
./scripts/generate-local-secrets.sh
./scripts/bootstrap.sh --reset --yes
./scripts/bootstrap-admin-panel.sh
open http://localhost:3000/admin
```

## Roadmap

Para que el core sea verdaderamente operativo sin tocar código:

- [x] **CRUD de Roles** — crear rol custom, editar metadata, asignar
  permisos a roles desde la UI (Fase 2).
- [x] **CRUD de Permisos** — catálogo + asignación a roles + invalidación
  de cache automática (Fase 2).
- [ ] **Module discovery automático (Fase 3)** — cada módulo declara
  `manifest.json` con su nombre, prefijo de URL, capability, label.
  El core escanea al arranque y registra routers + sidebar items sin
  hardcoding.

## Documentación

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — arquitectura modular, add-on
  model, cómo agregar módulos.
- [`INSTALL.md`](INSTALL.md) — instalación local + producción.
- [`docs/runbooks/`](docs/runbooks/) — guías operativas.

## Licencia

Propietario — uso interno Agente Copiloto IA.
