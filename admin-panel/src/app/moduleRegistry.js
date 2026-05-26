/**
 * Registro de módulos del panel — branch `core`.
 *
 * Solo contiene los módulos TRANSVERSALES del sistema operativo:
 *   - **Platform admin** (cross-tenant, solo platform_owner): fleet,
 *     system-health, billing, incidents, fleet-dlq, runbooks, roles-acl,
 *     feature-flags, ai-providers.
 *   - **Tenant transversales** (cualquier owner/admin del tenant):
 *     tenant-setup, team, legal, audit.
 *
 * Los módulos de producto (GD, influencer, chatbot) se "instalan" sobre
 * el core agregando sus propias entradas a este registry vía un hook de
 * carga dinámica (TODO Fase 2 — module discovery). El core NO conoce
 * estos módulos por nombre.
 *
 * El router (`router.jsx`) renderiza cada entrada vía `<ModuleScreen/>`,
 * que envuelve el componente en `<RequirePermission capability mode>`
 * cuando `capability` no es `null`.
 *
 * @type {Record<string, { Component: Function, capability: string|null, mode?: 'R'|'RW' }>}
 */

// ─── Platform admin (cross-tenant) ──────────────────────────────────────────
import { BillingMrr } from '../features/platform/billing-mrr/index.js';
import { FeatureFlags } from '../features/platform/feature-flags/index.js';
import { FleetDlq } from '../features/platform/fleet-dlq/index.js';
import { FleetTenants } from '../features/platform/fleet-tenants/index.js';
import { Incidents } from '../features/platform/incidents/index.js';
import { RolesAcl } from '../features/platform/roles-acl/index.js';
import { Runbooks } from '../features/platform/runbooks/index.js';
import { SystemHealth } from '../features/platform/system-health/index.js';
import { AIProvidersContainer } from '../features/platform/ai-providers/AIProvidersContainer.jsx';

// ─── Tenant transversales ───────────────────────────────────────────────────
import { AuditPanel } from '../features/owner-admin/audit/index.js';
import { LegalModule } from '../features/owner-admin/legal/index.js';
import { TeamModule } from '../features/owner-admin/team/index.js';
import { TenantSetupWizard } from '../features/owner-admin/tenant-setup/index.js';

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
  legal: { Component: LegalModule, capability: 'legal.write', mode: 'RW' },
  audit: { Component: AuditPanel, capability: 'audit.read' },
});
