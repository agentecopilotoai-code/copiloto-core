import { useEffect, useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { listMyTenants } from '../../services/coreApi.js';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { TenantSetupWizard } from '../modules/tenantSetup/TenantSetupWizard.jsx';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

function isSystemOwner(profile) {
  return Boolean(profile?.support_mode && profile?.roles?.includes('owner'));
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

  const activeContent = activeModuleId === 'tenant-setup' ? (
    <TenantSetupWizard
      module={activeModule}
      onTenantCreated={handleTenantCreated}
      session={session}
      tenant={activeTenant}
    />
  ) : hasTenant ? (
    <ModulePlaceholder module={activeModule} tenant={activeTenant} />
  ) : (
    <NoTenantOnboarding onCreateTenant={openTenantCreation} />
  );

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
