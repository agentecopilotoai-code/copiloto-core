import { useEffect, useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { listMyTenants } from '../../services/coreApi.js';
import { AuditPanel } from '../modules/audit/AuditPanel.jsx';
import { ContactsModule } from '../modules/contacts/ContactsModule.jsx';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { KnowledgeStudio } from '../modules/knowledge/KnowledgeStudio.jsx';
import { KnowledgeStorageSettings } from '../modules/knowledgeStorage/KnowledgeStorageSettings.jsx';
import { GoLiveReadiness } from '../modules/readiness/GoLiveReadiness.jsx';
import { OperationsDesk } from '../modules/operations/OperationsDesk.jsx';
import { ServiceCatalog } from '../modules/services/ServiceCatalog.jsx';
import { TenantSetupWizard } from '../modules/tenantSetup/TenantSetupWizard.jsx';
import { WhatsAppOnboarding } from '../modules/whatsapp/WhatsAppOnboarding.jsx';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

const PRIVILEGED_ROLES = new Set(['admin', 'owner', 'platform_owner']);

function isSystemOwner(profile) {
  return Boolean(profile?.support_mode && profile?.roles?.includes('owner'));
}

function isPrivilegedProfile(profile) {
  return (profile?.roles || []).some((r) => PRIVILEGED_ROLES.has(r));
}

function MfaRequiredBanner({ onDismiss }) {
  return (
    <div className="mfa-required-overlay">
      <div className="mfa-required-card">
        <div className="mfa-required-icon" aria-hidden="true">🔐</div>
        <h2 className="mfa-required-title">Verificacion en dos pasos recomendada</h2>
        <p className="mfa-required-body">
          Tu sesion tiene acceso privilegiado (<strong>admin</strong> /{' '}
          <strong>owner</strong>) pero no se detecto autenticacion de segundo
          factor (MFA). Se recomienda reiniciar sesion con MFA habilitado en
          Auth0 para mayor seguridad.
        </p>
        <p className="mfa-required-hint">
          Si no tienes Auth0 configurado o estas en desarrollo local, puedes
          continuar sin MFA. Si Auth0 esta activo, cierra sesion y reiniciala
          para que solicite el segundo factor.
        </p>
        <div className="mfa-required-actions">
          <form method="post" action="/admin/logout">
            <button className="mfa-required-action" type="submit">
              Cerrar sesion
            </button>
          </form>
          <button className="mfa-required-skip" type="button" onClick={onDismiss}>
            Continuar sin MFA
          </button>
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

  // Show MFA warning only when the server explicitly signals it (Auth0 active +
  // privileged role + no MFA).  Dismissable so local/dev setups are not blocked.
  const mfaWarning = session.mfa_required === true;
  const [mfaDismissed, setMfaDismissed] = useState(false);

  const initialTenantOptions = useTenantOptions(profile);
  const [tenantOptions, setTenantOptions] = useState(initialTenantOptions);
  const [activeTenantId, setActiveTenantId] = useState(initialTenantOptions[0]?.id);
  const canSwitchTenants = isSystemOwner(profile) && tenantOptions.length > 1;
  const hasTenant = tenantOptions.length > 0;


  useEffect(() => {
    let mounted = true;

    listMyTenants(session)
      .then((tenants) => {
        if (!mounted || !tenants.length) return;
        const nextOptions = tenants.map((tenant) => ({
          id: tenant.id,
          label: `${tenant.slug || tenant.display_name} · ${tenant.id}`,
        }));
        setTenantOptions(nextOptions);
        setActiveTenantId((currentTenantId) => currentTenantId || nextOptions[0]?.id);
      })
      .catch(() => {
        // If the user has no tenant yet, the onboarding card remains visible.
      });

    return () => {
      mounted = false;
    };
  }, [session]);

  const activeTenant = useMemo(
    () => tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0],
    [activeTenantId, tenantOptions],
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
  } else if (activeModuleId === 'services') {
    activeContent = <ServiceCatalog module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'whatsapp') {
    activeContent = <WhatsAppOnboarding module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'knowledge-storage') {
    activeContent = <KnowledgeStorageSettings module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'knowledge-studio') {
    activeContent = <KnowledgeStudio module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'contacts') {
    activeContent = <ContactsModule module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'operations-desk') {
    activeContent = <OperationsDesk module={activeModule} session={session} tenant={activeTenant} />;
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
  } else if (activeModuleId === 'audit') {
    activeContent = <AuditPanel module={activeModule} session={session} tenant={activeTenant} />;
  } else {
    activeContent = <ModulePlaceholder module={activeModule} tenant={activeTenant} />;
  }

  return (
    <>
      {mfaWarning && !mfaDismissed && (
        <MfaRequiredBanner onDismiss={() => setMfaDismissed(true)} />
      )}
    <main className="admin-shell">
      <Sidebar
        activeModuleId={activeModuleId}
        activeTenantId={activeTenantId}
        canSwitchTenants={canSwitchTenants}
        modules={modules}
        onModuleSelect={handleModuleSelect}
        onTenantChange={setActiveTenantId}
        tenantOptions={tenantOptions}
      />
      <section className="workspace">
        <Topbar activeModule={activeModule} profile={profile} />
        {activeContent}
      </section>
    </main>
    </>
  );
}
