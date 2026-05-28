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

/**
 * Q-7 (audit #3) — helper para `lazy()` con named export.
 *
 * `React.lazy()` requiere `{ default: Component }` pero nuestros módulos
 * exportan por nombre (`export { TeamModule }` desde `index.js`). Helper
 * reduce 10 líneas repetidas de `.then(m => ({ default: m.X }))`.
 *
 * @param {() => Promise<Record<string, any>>} importFn - función que retorna `import()`.
 * @param {string} exportName - nombre del export en el módulo target.
 * @returns componente lazy renderable.
 */
const lazyNamed = (importFn, exportName) =>
  lazy(() => importFn().then((m) => ({ default: m[exportName] })));

// ─── Platform admin (cross-tenant) — lazy ───────────────────────────────────
// Cada `lazyNamed(...)` queda como un chunk separado del bundle de Vite.
const BillingMrr = lazyNamed(() => import('../features/platform/billing-mrr/index.js'), 'BillingMrr');
const FeatureFlags = lazyNamed(() => import('../features/platform/feature-flags/index.js'), 'FeatureFlags');
const FleetDlq = lazyNamed(() => import('../features/platform/fleet-dlq/index.js'), 'FleetDlq');
const FleetTenants = lazyNamed(() => import('../features/platform/fleet-tenants/index.js'), 'FleetTenants');
const Incidents = lazyNamed(() => import('../features/platform/incidents/index.js'), 'Incidents');
const RolesAcl = lazyNamed(() => import('../features/platform/roles-acl/index.js'), 'RolesAcl');
const Runbooks = lazyNamed(() => import('../features/platform/runbooks/index.js'), 'Runbooks');
const SystemHealth = lazyNamed(() => import('../features/platform/system-health/index.js'), 'SystemHealth');
const AIProvidersContainer = lazyNamed(
  () => import('../features/platform/ai-providers/AIProvidersContainer.jsx'),
  'AIProvidersContainer',
);
// v2.0.0 — Email providers (multi-provider con fallback chain).
const EmailProvidersContainer = lazyNamed(
  () => import('../features/platform/email-providers/EmailProvidersContainer.jsx'),
  'EmailProvidersContainer',
);

// ─── Tenant transversales — lazy ────────────────────────────────────────────
const TeamModule = lazyNamed(() => import('../features/owner-admin/team/index.js'), 'TeamModule');
const TenantSetupWizard = lazyNamed(
  () => import('../features/owner-admin/tenant-setup/index.js'),
  'TenantSetupWizard',
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
  // v2.0.0 — Email providers (multi-provider, fallback chain).
  'platform-email-providers': {
    Component: EmailProvidersContainer,
    capability: 'platform.ai_providers.configure',
    mode: 'RW',
  },

  // Tenant transversales (administración del tenant en sí, no de un producto).
  'tenant-setup': { Component: TenantSetupWizard, capability: null },
  team: { Component: TeamModule, capability: 'team.write', mode: 'RW' },
});
