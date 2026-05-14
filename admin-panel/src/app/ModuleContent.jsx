import { RequirePermission } from '../permissions/index.js';
import { NoTenantOnboarding } from '../components/domain/NoTenantOnboarding.jsx';
import { AnalyticsPanel } from '../components/modules/analytics/AnalyticsPanel.jsx';
import { AuditPanel } from '../components/modules/audit/AuditPanel.jsx';
import { BranchesModule } from '../components/modules/branches/BranchesModule.jsx';
import { CampaignsModule } from '../components/modules/campaigns/CampaignsModule.jsx';
import { ContactsModule } from '../components/modules/contacts/ContactsModule.jsx';
import { KnowledgeStudio } from '../components/modules/knowledge/KnowledgeStudio.jsx';
import { KnowledgeStorageSettings } from '../components/modules/knowledgeStorage/KnowledgeStorageSettings.jsx';
import { LegalModule } from '../components/modules/legal/LegalModule.jsx';
import { MediaLibraryModule } from '../components/modules/media/MediaLibraryModule.jsx';
import { ModulePlaceholder } from '../components/modules/ModulePlaceholder.jsx';
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
 * Resuelve el contenido del módulo activo a partir de su `id`, envuelto en el
 * `<RequirePermission>` que corresponde a su capability.
 *
 * Puente temporal: este switch reemplaza al `if/else` que vivía dentro de
 * `AdminLayout`. UI-003 lo sustituye por el router declarativo (`react-router`)
 * y este archivo se elimina.
 *
 * @param {{
 *   activeModule: object,
 *   activeModuleId?: string,
 *   permissions: object,
 *   session: object,
 *   tenant?: object,
 *   hasTenant: boolean,
 *   tenantSetupInitialTab?: string|null,
 *   onTenantCreated: (tenant: object) => void,
 *   onNavigate: (moduleId: string) => void,
 *   onOpenTenantSetupTab: (tab: string) => void,
 * }} props
 */
export function ModuleContent({
  activeModule,
  activeModuleId,
  permissions,
  session,
  tenant,
  hasTenant,
  tenantSetupInitialTab,
  onTenantCreated,
  onNavigate,
  onOpenTenantSetupTab,
}) {
  if (activeModuleId === 'tenant-setup') {
    return (
      <TenantSetupWizard
        initialTab={tenantSetupInitialTab}
        module={activeModule}
        onTenantCreated={onTenantCreated}
        session={session}
        tenant={tenant}
      />
    );
  }

  if (!hasTenant) {
    return <NoTenantOnboarding onCreateTenant={() => onNavigate('tenant-setup')} />;
  }

  switch (activeModuleId) {
    case 'onboarding-wizard':
      return (
        <RequirePermission permissions={permissions} capability="onboarding.run" mode="RW">
          <OnboardingWizard
            module={activeModule}
            session={session}
            tenant={tenant}
            onNavigateToModule={onNavigate}
          />
        </RequirePermission>
      );
    case 'services':
      return (
        <RequirePermission permissions={permissions} capability="services.read">
          <ServiceCatalog module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'branches':
      return (
        <RequirePermission permissions={permissions} capability="branches.write" mode="RW">
          <BranchesModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'packages':
      return (
        <RequirePermission permissions={permissions} capability="packages.write" mode="RW">
          <PackagesModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'subscriptions':
      return (
        <RequirePermission permissions={permissions} capability="subscriptions.write" mode="RW">
          <SubscriptionsModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'whatsapp':
      return (
        <RequirePermission permissions={permissions} capability="whatsapp.read">
          <WhatsAppOnboarding module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'social-channels':
      return (
        <RequirePermission permissions={permissions} capability="social_channels.write" mode="RW">
          <SocialChannelsModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'knowledge-storage':
      return (
        <RequirePermission permissions={permissions} capability="knowledge_storage.write" mode="RW">
          <KnowledgeStorageSettings module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'knowledge-studio':
      return (
        <RequirePermission permissions={permissions} capability="knowledge.read">
          <KnowledgeStudio module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'media-library':
      return (
        <RequirePermission permissions={permissions} capability="media.write" mode="RW">
          <MediaLibraryModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'contacts':
      return (
        <RequirePermission permissions={permissions} capability="contacts.view">
          <ContactsModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'segments':
      return (
        <RequirePermission permissions={permissions} capability="segments.write" mode="RW">
          <SegmentsModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'campaigns':
      return (
        <RequirePermission permissions={permissions} capability="campaigns.write" mode="RW">
          <CampaignsModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'operations-desk':
      return (
        <RequirePermission permissions={permissions} capability="conversations.view">
          <OperationsDesk module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'outbound-dlq':
      return (
        <RequirePermission permissions={permissions} capability="outbound_dlq.retry" mode="RW">
          <OutboundDLQ module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'go-live-readiness':
      return (
        <RequirePermission permissions={permissions} capability="go_live_readiness.read">
          <GoLiveReadiness
            module={activeModule}
            onGoToEscalation={() => onOpenTenantSetupTab('escalation')}
            session={session}
            tenant={tenant}
          />
        </RequirePermission>
      );
    case 'analytics':
      return (
        <RequirePermission permissions={permissions} capability="analytics.tenant.read">
          <AnalyticsPanel module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'audit':
      return (
        <RequirePermission permissions={permissions} capability="audit.read">
          <AuditPanel module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'team':
      return (
        <RequirePermission permissions={permissions} capability="team.write" mode="RW">
          <TeamModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    case 'legal':
      return (
        <RequirePermission permissions={permissions} capability="legal.write" mode="RW">
          <LegalModule module={activeModule} session={session} tenant={tenant} />
        </RequirePermission>
      );
    default:
      return <ModulePlaceholder module={activeModule} tenant={tenant} />;
  }
}
