import { useEffect, useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { listMyTenants } from '../../services/coreApi.js';
import { AuditPanel } from '../modules/audit/AuditPanel.jsx';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { KnowledgeStudio } from '../modules/knowledge/KnowledgeStudio.jsx';
import { KnowledgeStorageSettings } from '../modules/knowledgeStorage/KnowledgeStorageSettings.jsx';
import { GoLiveReadiness } from '../modules/readiness/GoLiveReadiness.jsx';
import { OperationsDesk } from '../modules/operations/OperationsDesk.jsx';
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

function MfaRequiredBanner() {
  return (
    <div className="mfa-required-overlay">
      <div className="mfa-required-card">
        <div className="mfa-required-icon" aria-hidden="true">🔐</div>
        <h2 className="mfa-required-title">Verificacion en dos pasos requerida</h2>
        <p className="mfa-required-body">
          Tu sesion tiene acceso privilegiado (<strong>admin</strong> /{' '}
          <strong>owner</strong>) pero no se completo la autenticacion de segundo
          factor (MFA). Por seguridad, debes iniciar sesion nuevamente con MFA
          habilitado en Auth0.
        </p>
        <p className="mfa-required-hint">
          Si ya tienes MFA configurado en tu cuenta, cierra sesion y vuelve a
          iniciarla para que Auth0 solicite el segundo factor.
        </p>
        <form method="post" action="/admin/logout">
          <button className="mfa-required-action" type="submit">
            Cerrar sesion e iniciar con MFA
          </button>
        </form>
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
  const profile = session.profile;

  // Block privileged sessions that completed login without MFA.
  const mfaRequired =
    session.mfa_required === true ||
    (isPrivilegedProfile(profile) && profile?.mfa_verified === false);

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

  function openTenantCreation() {
    selectModule('tenant-setup');
  }

  if (mfaRequired) {
    return <MfaRequiredBanner />;
  }

  let activeContent;
  if (activeModuleId === 'tenant-setup') {
    activeContent = (
      <TenantSetupWizard
        module={activeModule}
        onTenantCreated={handleTenantCreated}
        session={session}
        tenant={activeTenant}
      />
    );
  } else if (!hasTenant) {
    activeContent = <NoTenantOnboarding onCreateTenant={openTenantCreation} />;
  } else if (activeModuleId === 'whatsapp') {
    activeContent = <WhatsAppOnboarding module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'knowledge-storage') {
    activeContent = <KnowledgeStorageSettings module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'knowledge-studio') {
    activeContent = <KnowledgeStudio module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'operations-desk') {
    activeContent = <OperationsDesk module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'go-live-readiness') {
    activeContent = <GoLiveReadiness module={activeModule} session={session} tenant={activeTenant} />;
  } else if (activeModuleId === 'audit') {
    activeContent = <AuditPanel module={activeModule} session={session} tenant={activeTenant} />;
  } else {
    activeContent = <ModulePlaceholder module={activeModule} tenant={activeTenant} />;
  }

  return (
    <main className="admin-shell">
      <Sidebar
        activeModuleId={activeModuleId}
        activeTenantId={activeTenantId}
        canSwitchTenants={canSwitchTenants}
        modules={modules}
        onModuleSelect={selectModule}
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
