# Copiloto Core

> **Sistema operativo multi-tenant para construir SaaS de productos verticales.**

Copiloto Core es la base sobre la cual cualquier producto SaaS multi-tenant
se construye: autenticación con Auth0 + MFA, gestión de tenants, control
de membresía, configuración cross-modal de proveedores IA, runbooks,
incidentes, monitor de salud, billing & MRR, feature flags, matriz de
roles & permisos. **El core nunca conoce productos** — los productos
(GD, Influencer, Chatbot, etc.) se instalan encima sin modificarlo.

## ¿Qué incluye el core?

### Backend (`app/`)
- **`app/core/`** — auth, identity, config, logging. Transversal.
- **`app/db/`** — pool asyncpg + helpers RLS multi-tenant.
- **`app/ai/`** — registry de proveedores LLM/Image/Video/TTS/STT.
- **`app/admin/`** — BFF del admin-panel (Auth0 + session cookies +
  proxy a la Core API).
- **`app/platform_admin/`** — endpoints platform-owner-only
  (`/v1/platform/ai-providers/*`, `/v1/platform/tenant-modules/*`).
- **`app/api/v1/handlers/`** — endpoints transversales: `public`,
  `system`, `me`, `tenant_signup`, `tenant_user`, `tenant_catalog`,
  `tenant_ops`, `tenant_manager`, `tenant_analytics`, `platform_admin`.
- **`app/services/`** — utilidades transversales: audit, metrics,
  rate_limit, retention, feature_flags, platform_*.

### Frontend (`admin-panel/`)
- **Platform admin** completo: Fleet, System Health, Billing & MRR,
  Incidents, Outbound DLQ, Runbooks, Roles & ACL, Feature flags,
  Proveedores IA.
- **Tenant transversales**: Configuración del tenant, Equipo, Legal,
  Auditoría.
- **"Mi cuenta"**: perfil, preferencias, notificaciones, sesiones.

### Infraestructura (`infra/postgres/`)
- **`10-core.sql`** — schema `app.*` con RLS, tenant_modules,
  platform_ai_providers, feature_flags, audit_logs, …

## ¿Cómo se instala un producto sobre el core?

Cada producto vive en su propio paquete (`app/<modulo>/`) y subdirectorio
de features (`admin-panel/src/features/<modulo>/`), con su SQL aislado
en `infra/postgres/modules/<modulo>.sql`. La activación es por tenant:
una fila en `app.tenant_modules (tenant_id, module, enabled)`.

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) § "Cómo agregar un
módulo nuevo (checklist)".

## Branches relacionados

Este repo es el **core puro**. Branches de productos viven en otros
repos:

| Repo                                | Contiene                                          |
| ----------------------------------- | ------------------------------------------------- |
| `copiloto-core` (este)              | Solo core                                         |
| `CopilotoIA` (develop)              | Core + Chatbot + Influencer + GD (full dev)       |
| `CopilotoIA` (gestion-documental)   | Core + Gestión Documental (white-label gobierno)  |

## Quick start

```bash
git clone https://github.com/agentecopilotoai-code/copiloto-core.git
cd copiloto-core
cp .env.example .env  # configurar Auth0 + DB
./scripts/bootstrap.sh --reset --yes
./scripts/bootstrap-admin-panel.sh
open http://localhost:3000/admin
```

## Roadmap (Fase 2 — CRUDs)

Para que el core sea verdaderamente operativo sin tocar código:

- [ ] **CRUD de Roles** — crear rol custom, editar metadata, asignar
  permisos a roles desde la UI.
- [ ] **CRUD de Permisos** — catálogo + asignación a roles + invalidación
  de cache automática.
- [ ] **CRUD de Módulos** — registrar módulo nuevo en el catálogo,
  activar/desactivar por tenant.
- [ ] **CRUD de Feature Flags** — write (hoy solo read).
- [ ] **Module discovery automático** — cada módulo declara
  `manifest.json` con su nombre, prefijo de URL, capability, label.
  El core escanea al arranque y registra routers + sidebar items sin
  hardcoding.

## Documentación

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitectura modular,
  add-on model, cómo agregar módulos.
- [`docs/ADMIN_PANEL.md`](docs/ADMIN_PANEL.md) — admin-panel + Auth0.
- [`docs/runbooks/`](docs/runbooks/) — guías operativas.

## Licencia

Propietario — uso interno Agente Copiloto IA.
