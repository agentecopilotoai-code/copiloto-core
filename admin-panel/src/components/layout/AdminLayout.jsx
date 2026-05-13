import { useEffect, useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { listMyTenants } from '../../services/coreApi.js';
import { AnalyticsPanel } from '../modules/analytics/AnalyticsPanel.jsx';
import { AuditPanel } from '../modules/audit/AuditPanel.jsx';
import { CampaignsModule } from '../modules/campaigns/CampaignsModule.jsx';
import { ContactsModule } from '../modules/contacts/ContactsModule.jsx';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { KnowledgeStudio } from '../modules/knowledge/KnowledgeStudio.jsx';
import { KnowledgeStorageSettings } from '../modules/knowledgeStorage/KnowledgeStorageSettings.jsx';
import { MediaLibraryModule } from '../modules/media/MediaLibraryModule.jsx';
import { GoLiveReadiness } from '../modules/readiness/GoLiveReadiness.jsx';
import { OperationsDesk } from '../modules/operations/OperationsDesk.jsx';
import { OutboundDLQ } from '../modules/outbound/OutboundDLQ.jsx';
import { BranchesModule } from '../modules/branches/BranchesModule.jsx';
import { PackagesModule } from '../modules/packages/PackagesModule.jsx';
import { SubscriptionsModule } from '../modules/subscriptions/SubscriptionsModule.jsx';
import { SegmentsModule } from '../modules/segments/SegmentsModule.jsx';
import { ServiceCatalog } from '../modules/services/ServiceCatalog.jsx';
import { TeamModule } from '../modules/team/TeamModule.jsx';
import { LegalModule } from '../modules/legal/LegalModule.jsx';
import { TenantSetupWizard } from '../modules/tenantSetup/TenantSetupWizard.jsx';
import { OnboardingWizard } from '../modules/onboarding/OnboardingWizard.jsx';
import { WhatsAppOnboarding } from '../modules/whatsapp/WhatsAppOnboarding.jsx';
import { SocialChannelsModule } from '../modules/socialChannels/SocialChannelsModule.jsx';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

const PRIVILEGED_ROLES = new Set(['admin', 'owner', 'platform_owner']);
const ROLE_LEVELS = { viewer: 5, agent: 10, manager: 20, admin: 30, owner: 40, platform_owner: 50, support: 50 };

function isSystemOwner(profile) {
  return Boolean(profile?.support_mode && profile?.roles?.includes('owner'));
}

function isPrivilegedProfile(profile) {
  return (profile?.roles || []).some((r) => PRIVILEGED_ROLES.has(r));
}

function highestRole(roles) {
  const order = ['owner', 'admin', 'manager', 'agent', 'viewer'];
  for (const role of order) {
    if (roles?.includes(role)) return role;
  }
  return roles?.[0] || 'viewer';
}

function hasMinRole(roles, minRole) {
  if (!minRole) return true;
  const required = ROLE_LEVELS[minRole] ?? 0;
  return (roles || []).some((r) => (ROLE_LEVELS[r] ?? 0) >= required);
}

function MfaRequiredBlocker() {
  return (
    <div className="mfa-required-overlay" role="alertdialog" aria-modal="true">
      <div className="mfa-required-card">
        <div className="mfa-required-icon" aria-hidden="true">🔐</div>
        <h2 className="mfa-required-title">Verificación en dos pasos obligatoria</h2>
        <p className="mfa-required-body">
          Tu sesión tiene acceso privilegiado (<strong>admin</strong> /{' '}
          <strong>owner</strong> / <strong>platform_owner</strong>) pero no se
          detectó autenticación de segundo factor (MFA). El servidor rechazará
          cualquier operación privilegiada con <code>403 mfa_required</code>
          hasta que reinicies sesión con MFA habilitado en Auth0.
        </p>
        <p className="mfa-required-hint">
          Cierra sesión y vuelve a entrar; Auth0 te pedirá el segundo factor
          configurado en tu cuenta.
        </p>
        <div className="mfa-required-actions">
          <form method="post" action="/admin/logout">
            <button className="mfa-required-action" type="submit">
              Cerrar sesión
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function NoTenantOnboarding({ onCreateTenant }) {
  return (
    <section className="module-card empty-tenant-card">
      <p className="eyebrow">Primer tenant</p>
      <h2>Crea tu tenant para empezar</h2>
      <p className="hint">
        Tu usuario todavía no está asociado a un tenant. Crea uno y quedarás como su
        administrador principal para continuar la configuración.
      </p>
      <button className="primary-action" onClick={onCreateTenant} type="button">
        Crear tenant
      </button>
    </section>
  );
}

export function AdminLayout({ session }) {
  const { activeModule, activeModuleId, modules, selectModule } = useActiveModule();
  const [tenantSetupInitialTab, setTenantSetupInitialTab] = useState(null);
  const profile = session.profile;

  // TASK-0080 / BUG14: when the server reports mfa_required=true we hard
  // block the panel — no children render until the user logs out and
  // reauthenticates with MFA. The gate is non-dismissable and matches the
  // server-side 403 the BFF proxy now returns.
  const mfaRequired = session.mfa_required === true;

  const initialTenantOptions = useTenantOptions(profile);
  const [tenantOptions, setTenantOptions] = useState(initialTenantOptions);
  const [activeTenantId, setActiveTenantId] = useState(initialTenantOptions[0]?.id);
  // Multi-tenant switcher (Slack-style): show whenever the user belongs to
  // more than one tenant, regardless of support mode.
  const canSwitchTenants = tenantOptions.length > 1 || isSystemOwner(profile);
  const hasTenant = tenantOptions.length > 0;


  useEffect(() => {
    let mounted = true;

    listMyTenants(session)
      .then((tenants) => {
        if (!mounted || !tenants.length) return;
        const nextOptions = tenants.map((tenant) => ({
          id: tenant.id,
          slug: tenant.slug,
          display_name: tenant.display_name,
          roles: tenant.roles || (tenant.role ? [tenant.role] : []),
          role: tenant.role || highestRole(tenant.roles),
          is_default: Boolean(tenant.is_default),
          label: `${tenant.slug || tenant.display_name || 'tenant'} · ${highestRole(tenant.roles) || 'viewer'}`,
        }));
        setTenantOptions(nextOptions);
        setActiveTenantId((currentTenantId) => {
          if (currentTenantId && nextOptions.some((t) => t.id === currentTenantId)) {
            return currentTenantId;
          }
          const stored = window.localStorage?.getItem('copilotoia.activeTenantId');
          if (stored && nextOptions.some((t) => t.id === stored)) return stored;
          return nextOptions.find((t) => t.is_default)?.id || nextOptions[0]?.id;
        });
      })
      .catch(() => {
        // If the user has no tenant yet, the onboarding card remains visible.
      });

    return () => {
      mounted = false;
    };
  }, [session]);

  useEffect(() => {
    if (activeTenantId) {
      try {
        window.localStorage?.setItem('copilotoia.activeTenantId', activeTenantId);
      } catch {
        /* ignore storage errors */
      }
    }
  }, [activeTenantId]);

  const activeTenant = useMemo(
    () => tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0],
    [activeTenantId, tenantOptions],
  );

  const activeRoles = useMemo(() => {
    const fromTenant = activeTenant?.roles || (activeTenant?.role ? [activeTenant.role] : []);
    // Platform owners with support_mode keep their privileges across tenants.
    const fromProfile = isSystemOwner(profile) ? profile?.roles || [] : [];
    return Array.from(new Set([...fromTenant, ...fromProfile]));
  }, [activeTenant, profile]);

  const visibleModules = useMemo(
    () => modules.filter((module) => hasMinRole(activeRoles, module.minRole)),
    [modules, activeRoles],
  );

  function handleTenantCreated(createdTenant) {
    setTenantOptions((currentOptions) => {
      const nextTenant = {
        ...createdTenant,
        label: createdTenant.label || `${createdTenant.slug} · ${createdTenant.id}`,
      };
      if (currentOptions.some((option) => option.id === createdTenant.id)) {
        return currentOptions.map((option) => (option.id === createdTenant.id ? nextTenant : option));
      }
      return [...currentOptions, nextTenant];
    });
    setActiveTenantId(createdTenant.id);
  }

  function handleModuleSelect(moduleId) {
    if (moduleId === 'tenant-setup') setTenantSetupInitialTab(null);
    selectModule(moduleId);
  }

  function openTenantCreation() {
    setTenantSetupInitialTab(null);
    selectModule('tenant-setup');
  }

  let activeContent;
  if (activeModuleId === 'tenant-setup') {
    activeContent = (
      <TenantSetupWizard
        initialTab={tenantSetupInitialTab}
        module={activeModule}
        onTenantCreated={handleTenantCreated}
        session={session}
        tenant={activeTenant}
      />
    );
  } else if (!hasTenant) {
    activeContent = <NoTenantOnboarding onCreateTenant={openTenantCreation} />;
  } else if (activeModuleId === 'onboarding-wizard') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para correr
            el wizard de onboarding.
          </p>
        </section>
      );
    } else {
      activeContent = (
        <OnboardingWizard
          module={activeModule}
          session={session}
          tenant={activeTenant}
          onNavigateToModule={(targetModuleId) => {
            if (targetModuleId === 'tenant-setup') setTenantSetupInitialTab(null);
            selectModule(targetModuleId);
          }}
        />
      );
    }
  } else if (activeModuleId === 'services') {
    activeContent = <ServiceCatalog module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'branches') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            las sedes.
          </p>
        </section>
      );
    } else {
      activeContent = <BranchesModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'packages') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            los paquetes y planes de tratamiento.
          </p>
        </section>
      );
    } else {
      activeContent = <PackagesModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'subscriptions') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            las suscripciones recurrentes.
          </p>
        </section>
      );
    } else {
      activeContent = <SubscriptionsModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'whatsapp') {
    activeContent = <WhatsAppOnboarding module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'social-channels') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            los canales sociales (Instagram DM y Facebook Messenger).
          </p>
        </section>
      );
    } else {
      activeContent = <SocialChannelsModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'knowledge-storage') {
    activeContent = <KnowledgeStorageSettings module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'knowledge-studio') {
    activeContent = <KnowledgeStudio module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'media-library') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            la biblioteca de medios y promociones.
          </p>
        </section>
      );
    } else {
      activeContent = <MediaLibraryModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'contacts') {
    activeContent = <ContactsModule module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'segments') {
    if (!hasMinRole(activeRoles, 'manager')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>manager</strong>, <strong>admin</strong> u <strong>owner</strong> en este
            tenant para gestionar segmentos.
          </p>
        </section>
      );
    } else {
      activeContent = <SegmentsModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'campaigns') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar
            campañas masivas. Cambia al tenant donde tengas permisos o pide a un admin que te promocione.
          </p>
        </section>
      );
    } else {
      activeContent = <CampaignsModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'operations-desk') {
    activeContent = <OperationsDesk module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'outbound-dlq') {
    activeContent = <OutboundDLQ module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'go-live-readiness') {
    activeContent = (
      <GoLiveReadiness
        module={activeModule}
        onGoToEscalation={() => {
          setTenantSetupInitialTab('escalation');
          selectModule('tenant-setup');
        }}
        session={session}
        tenant={activeTenant}
      />
    );
  } else if (activeModuleId === 'analytics') {
    activeContent = <AnalyticsPanel module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'audit') {
    activeContent = <AuditPanel module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'team') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar el
            equipo. Cambia al tenant donde tengas permisos o pide a un admin que te promocione.
          </p>
        </section>
      );
    } else {
      activeContent = <TeamModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else if (activeModuleId === 'legal') {
    if (!hasMinRole(activeRoles, 'admin')) {
      activeContent = (
        <section className="module-card">
          <h2>Acceso restringido</h2>
          <p className="hint">
            Necesitas rol <strong>admin</strong> u <strong>owner</strong> en este tenant para gestionar las
            páginas legales y los avisos de privacidad.
          </p>
        </section>
      );
    } else {
      activeContent = <LegalModule module={activeModule} session={session} tenant={activeTenant} />;
    }
  } else {
    activeContent = <ModulePlaceholder module={activeModule} tenant={activeTenant} />;
  }

  if (mfaRequired) {
    return <MfaRequiredBlocker />;
  }

  return (
    <main className="admin-shell">
      <Sidebar
        activeModuleId={activeModuleId}
        activeTenantId={activeTenantId}
        canSwitchTenants={canSwitchTenants}
        modules={visibleModules}
        onModuleSelect={handleModuleSelect}
        onTenantChange={setActiveTenantId}
        tenantOptions={tenantOptions}
      />
      <section className="workspace">
        <Topbar activeModule={activeModule} profile={profile} />
        {activeContent}
      </section>
    </main>
  );
}
