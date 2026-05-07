import { useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { TenantSetupWizard } from '../modules/tenantSetup/TenantSetupWizard.jsx';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

export function AdminLayout({ session }) {
  const { activeModule, activeModuleId, modules, selectModule } = useActiveModule();
  const profile = session.profile;
  const initialTenantOptions = useTenantOptions(profile);
  const [tenantOptions, setTenantOptions] = useState(initialTenantOptions);
  const [activeTenantId, setActiveTenantId] = useState(initialTenantOptions[0]?.id);

  const activeTenant = useMemo(
    () => tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0],
    [activeTenantId, tenantOptions],
  );

  function handleTenantCreated(createdTenant) {
    setTenantOptions((currentOptions) => {
      if (currentOptions.some((option) => option.id === createdTenant.id)) {
        return currentOptions;
      }
      return [...currentOptions, createdTenant];
    });
    setActiveTenantId(createdTenant.id);
  }

  const activeContent = activeModuleId === 'tenant-setup' ? (
    <TenantSetupWizard
      module={activeModule}
      onTenantCreated={handleTenantCreated}
      session={session}
      tenant={activeTenant}
    />
  ) : (
    <ModulePlaceholder module={activeModule} tenant={activeTenant} />
  );

  return (
    <main className="admin-shell">
      <Sidebar
        activeModuleId={activeModuleId}
        activeTenantId={activeTenantId}
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
