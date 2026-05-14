import { BillingMrr } from '../features/platform/billing-mrr/index.js';
import { FleetDlq } from '../features/platform/fleet-dlq/index.js';
import { FleetTenants } from '../features/platform/fleet-tenants/index.js';
import { Incidents } from '../features/platform/incidents/index.js';
import { SystemHealth } from '../features/platform/system-health/index.js';
import { AnalyticsPanel } from '../components/modules/analytics/AnalyticsPanel.jsx';
import { AuditPanel } from '../components/modules/audit/AuditPanel.jsx';
import { BranchesModule } from '../components/modules/branches/BranchesModule.jsx';
import { CampaignsModule } from '../components/modules/campaigns/CampaignsModule.jsx';
import { ContactsModule } from '../components/modules/contacts/ContactsModule.jsx';
import { KnowledgeStudio } from '../components/modules/knowledge/KnowledgeStudio.jsx';
import { KnowledgeStorageSettings } from '../components/modules/knowledgeStorage/KnowledgeStorageSettings.jsx';
import { LegalModule } from '../components/modules/legal/LegalModule.jsx';
import { MediaLibraryModule } from '../components/modules/media/MediaLibraryModule.jsx';
import { OnboardingWizard } from '../components/modules/onboarding/OnboardingWizard.jsx';
import { OperationsDesk } from '../components/modules/operations/OperationsDesk.jsx';
import { OutboundDLQ } from '../components/modules/outbound/OutboundDLQ.jsx';
import { PackagesModule } from '../components/modules/packages/PackagesModule.jsx';
import { GoLiveReadiness } from '../components/modules/readiness/GoLiveReadiness.jsx';
import { SegmentsModule } from '../components/modules/segments/SegmentsModule.jsx';
import { ServiceCatalog } from '../components/modules/services/ServiceCatalog.jsx';
import { SocialChannelsModule } from '../components/modules/socialChannels/SocialChannelsModule.jsx';
import { SubscriptionsModule } from '../components/modules/subscriptions/SubscriptionsModule.jsx';
import { TeamModule } from '../components/modules/team/TeamModule.jsx';
import { TenantSetupWizard } from '../components/modules/tenantSetup/TenantSetupWizard.jsx';
import { WhatsAppOnboarding } from '../components/modules/whatsapp/WhatsAppOnboarding.jsx';

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
  'tenant-setup': { Component: TenantSetupWizard, capability: null },
  'onboarding-wizard': { Component: OnboardingWizard, capability: 'onboarding.run', mode: 'RW' },
  services: { Component: ServiceCatalog, capability: 'services.read' },
  branches: { Component: BranchesModule, capability: 'branches.write', mode: 'RW' },
  packages: { Component: PackagesModule, capability: 'packages.write', mode: 'RW' },
  subscriptions: { Component: SubscriptionsModule, capability: 'subscriptions.write', mode: 'RW' },
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
  contacts: { Component: ContactsModule, capability: 'contacts.view' },
  segments: { Component: SegmentsModule, capability: 'segments.write', mode: 'RW' },
  campaigns: { Component: CampaignsModule, capability: 'campaigns.write', mode: 'RW' },
  'operations-desk': { Component: OperationsDesk, capability: 'conversations.view' },
  'outbound-dlq': { Component: OutboundDLQ, capability: 'outbound_dlq.retry', mode: 'RW' },
  'go-live-readiness': { Component: GoLiveReadiness, capability: 'go_live_readiness.read' },
  analytics: { Component: AnalyticsPanel, capability: 'analytics.tenant.read' },
  audit: { Component: AuditPanel, capability: 'audit.read' },
  team: { Component: TeamModule, capability: 'team.write', mode: 'RW' },
  legal: { Component: LegalModule, capability: 'legal.write', mode: 'RW' },
});
