/**
 * Registro de módulos del panel — branch `core`.
 *
 * Solo contiene los módulos TRANSVERSALES del sistema operativo:
 *   - **Platform admin** (cross-tenant, solo platform_owner): fleet,
 *     system-health, billing, incidents, fleet-dlq, runbooks, roles-acl,
 *     feature-flags, ai-providers.
 *   - **Tenant transversales** (cualquier owner/admin del tenant):
 *     tenant-setup, team.
 *
 * Los módulos de producto se "instalan" sobre el core agregando sus propias
 * entradas a este registry vía un hook de carga dinámica (TODO Fase 3 —
 * module discovery con manifest.json). El core NO conoce esos módulos por
 * nombre.
 *
 * El router (`router.jsx`) renderiza cada entrada vía `<ModuleScreen/>`,
 * que envuelve el componente en `<RequirePermission capability mode>`
 * cuando `capability` no es `null`.
 *
 * PERF-020 (audit #2, 2026-05-27) — los Components se cargan **lazy** via
 * `React.lazy()`. Esto permite a Vite hacer code-splitting automático:
 * cada módulo queda en su propio chunk JS. El bundle inicial cae de
 * ~391 KB (mono-bundle) a ~80 KB inicial + chunks por demanda. Cada
 * navegación carga su chunk async (cache HTTP-friendly). `<ModuleScreen/>`
 * envuelve el render en `<Suspense fallback={...} />` para mostrar
 * skeleton mientras carga.
 *
 * @type {Record<string, { Component: Function, capability: string|null, mode?: 'R'|'RW' }>}
 */
import { lazy } from 'react';

// ─── Platform admin (cross-tenant) — lazy ───────────────────────────────────
// Cada `lazy(() => import(...))` queda como un chunk separado del bundle
// de Vite. El default export de `index.js` se preserva, mantenemos el
// shape `{ Component }` igual.
const BillingMrr = lazy(() =>
  import('../features/platform/billing-mrr/index.js').then((m) => ({ default: m.BillingMrr })),
);
const FeatureFlags = lazy(() =>
  import('../features/platform/feature-flags/index.js').then((m) => ({ default: m.FeatureFlags })),
);
const FleetDlq = lazy(() =>
  import('../features/platform/fleet-dlq/index.js').then((m) => ({ default: m.FleetDlq })),
);
const FleetTenants = lazy(() =>
  import('../features/platform/fleet-tenants/index.js').then((m) => ({ default: m.FleetTenants })),
);
const Incidents = lazy(() =>
  import('../features/platform/incidents/index.js').then((m) => ({ default: m.Incidents })),
);
const RolesAcl = lazy(() =>
  import('../features/platform/roles-acl/index.js').then((m) => ({ default: m.RolesAcl })),
);
const Runbooks = lazy(() =>
  import('../features/platform/runbooks/index.js').then((m) => ({ default: m.Runbooks })),
);
const SystemHealth = lazy(() =>
  import('../features/platform/system-health/index.js').then((m) => ({ default: m.SystemHealth })),
);
const AIProvidersContainer = lazy(() =>
  import('../features/platform/ai-providers/AIProvidersContainer.jsx').then((m) => ({
    default: m.AIProvidersContainer,
  })),
);

// ─── Tenant transversales — lazy ────────────────────────────────────────────
const TeamModule = lazy(() =>
  import('../features/owner-admin/team/index.js').then((m) => ({ default: m.TeamModule })),
);
const TenantSetupWizard = lazy(() =>
  import('../features/owner-admin/tenant-setup/index.js').then((m) => ({
    default: m.TenantSetupWizard,
  })),
);

export const MODULE_REGISTRY = Object.freeze({
  'platform-fleet': { Component: FleetTenants, capability: 'platform.tenants.read' },
  'platform-system-health': {
    Component: SystemHealth,
    capability: 'platform.system_health.read',
  },
  'platform-billing': { Component: BillingMrr, capability: 'platform.billing.read' },
  'platform-incidents': { Component: Incidents, capability: 'platform.incidents.read' },
  'platform-fleet-dlq': { Component: FleetDlq, capability: 'platform.outbound_dlq.read' },
  'platform-runbooks': { Component: Runbooks, capability: 'platform.runbooks.read' },
  'platform-roles-acl': { Component: RolesAcl, capability: 'platform.roles_acl.read' },
  'platform-feature-flags': {
    Component: FeatureFlags,
    capability: 'platform.feature_flags.read',
  },
  // Proveedores IA — config transversal cross-modalidad (LLM/image/etc).
  // Alimenta cualquier módulo de producto que requiera IA.
  'platform-ai-providers': {
    Component: AIProvidersContainer,
    capability: 'platform.ai_providers.configure',
    mode: 'RW',
  },

  // Tenant transversales (administración del tenant en sí, no de un producto).
  'tenant-setup': { Component: TenantSetupWizard, capability: null },
  team: { Component: TeamModule, capability: 'team.write', mode: 'RW' },
});
