import { BillingMrr } from '../features/platform/billing-mrr/index.js';
import { FeatureFlags } from '../features/platform/feature-flags/index.js';
import { FleetDlq } from '../features/platform/fleet-dlq/index.js';
import { FleetTenants } from '../features/platform/fleet-tenants/index.js';
import { Incidents } from '../features/platform/incidents/index.js';
import { RolesAcl } from '../features/platform/roles-acl/index.js';
import { Runbooks } from '../features/platform/runbooks/index.js';
import { SystemHealth } from '../features/platform/system-health/index.js';
import { Dashboard } from '../features/owner-admin/dashboard/index.js';
import { Onboarding } from '../features/owner-admin/onboarding/index.js';
import { ConversationsContacts } from '../features/owner-admin/conversations-contacts/index.js';
import { Services } from '../features/owner-admin/services/index.js';
import { Packages } from '../features/owner-admin/packages/index.js';
import { Subscriptions } from '../features/owner-admin/subscriptions/index.js';
import { Branches } from '../features/owner-admin/branches/index.js';
import { WhatsAppOnboarding } from '../features/owner-admin/whatsapp/index.js';
import { AnalyticsPanel } from '../features/owner-admin/analytics/index.js';
import { ManagerAnalytics } from '../features/manager/analytics/index.js';
import { AuditPanel } from '../features/owner-admin/audit/index.js';
import { CampaignsModule } from '../features/manager/campaigns/index.js';
import { DigestReports } from '../features/manager/digest-reports/index.js';
import { KnowledgeStorageSettings } from '../features/owner-admin/knowledge-studio/components/KnowledgeStorageSettings.jsx';
import { KnowledgeStudio } from '../features/owner-admin/knowledge-studio/index.js';
import { LegalModule } from '../features/owner-admin/legal/index.js';
import { MediaLibraryModule } from '../features/owner-admin/media-library/index.js';
import { MyHandoffs } from '../features/agente/my-handoffs/index.js';
import { OperationsDesk } from '../features/agente/inbox/index.js';
import { OutboundDLQ } from '../features/agente/outbound-dlq/index.js';
import { TodayAppointments } from '../features/agente/today-appointments/index.js';
import { GoLiveReadiness } from '../features/owner-admin/readiness/index.js';
import { SegmentsModule } from '../features/manager/segments/index.js';
import { SocialChannelsModule } from '../features/owner-admin/social-channels/index.js';
import { TeamModule } from '../features/owner-admin/team/index.js';
import { TenantSetupWizard } from '../features/owner-admin/tenant-setup/index.js';
import { ViewerAnalytics } from '../features/viewer/analytics/index.js';
import { ViewerAppointments } from '../features/viewer/appointments/index.js';
import { ViewerConversations } from '../features/viewer/conversations/index.js';
import { ViewerSummary } from '../features/viewer/summary/index.js';

/**
 * Registro `module id → { Component, capability, mode }`.
 *
 * Reemplaza al `switch` que vivía en `ModuleContent.jsx`. El router
 * (`router.jsx`) renderiza cada entrada vía `<ModuleScreen/>`, que envuelve el
 * componente en `<RequirePermission capability mode>` cuando `capability` no es
 * `null`. Las capabilities espejan exactamente las del antiguo `ModuleContent`.
 *
 * Los ids que NO están aquí (p. ej. `platform-*`) se renderizan como
 * `<ModulePlaceholder/>`: las vistas reales llegan en UI-006..UI-010.
 *
 * @type {Record<string, { Component: Function, capability: string|null, mode?: 'R'|'RW' }>}
 */
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
  dashboard: { Component: Dashboard, capability: 'analytics.tenant.read' },
  'tenant-setup': { Component: TenantSetupWizard, capability: null },
  'onboarding-wizard': { Component: Onboarding, capability: 'onboarding.run', mode: 'RW' },
  services: { Component: Services, capability: 'services.read' },
  branches: { Component: Branches, capability: 'branches.write', mode: 'RW' },
  packages: { Component: Packages, capability: 'packages.write', mode: 'RW' },
  subscriptions: { Component: Subscriptions, capability: 'subscriptions.write', mode: 'RW' },
  whatsapp: { Component: WhatsAppOnboarding, capability: 'whatsapp.read' },
  'social-channels': {
    Component: SocialChannelsModule,
    capability: 'social_channels.write',
    mode: 'RW',
  },
  'knowledge-storage': {
    Component: KnowledgeStorageSettings,
    capability: 'knowledge_storage.write',
    mode: 'RW',
  },
  'knowledge-studio': { Component: KnowledgeStudio, capability: 'knowledge.read' },
  'media-library': { Component: MediaLibraryModule, capability: 'media.write', mode: 'RW' },
  contacts: { Component: ConversationsContacts, capability: 'contacts.view' },
  segments: { Component: SegmentsModule, capability: 'segments.write', mode: 'RW' },
  campaigns: { Component: CampaignsModule, capability: 'campaigns.write', mode: 'RW' },
  'operations-desk': { Component: OperationsDesk, capability: 'conversations.view' },
  'my-handoffs': { Component: MyHandoffs, capability: 'conversations.view' },
  'outbound-dlq': { Component: OutboundDLQ, capability: 'outbound_dlq.retry', mode: 'RW' },
  appointments: { Component: TodayAppointments, capability: 'appointments.view' },
  'go-live-readiness': { Component: GoLiveReadiness, capability: 'go_live_readiness.read' },
  analytics: { Component: AnalyticsPanel, capability: 'analytics.tenant.read' },
  'manager-analytics': {
    Component: ManagerAnalytics,
    capability: 'analytics.tenant.read',
  },
  'digest-reports': { Component: DigestReports, capability: 'digest.write', mode: 'RW' },
  audit: { Component: AuditPanel, capability: 'audit.read' },
  team: { Component: TeamModule, capability: 'team.write', mode: 'RW' },
  legal: { Component: LegalModule, capability: 'legal.write', mode: 'RW' },
  'viewer-summary': { Component: ViewerSummary, capability: 'analytics.tenant.read' },
  'viewer-analytics': { Component: ViewerAnalytics, capability: 'analytics.tenant.read' },
  'viewer-appointments': { Component: ViewerAppointments, capability: 'appointments.view' },
  'viewer-conversations': { Component: ViewerConversations, capability: 'conversations.view' },
});
