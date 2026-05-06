import { useMemo, useState } from 'react';

import { useActiveModule } from '../../hooks/useActiveModule.js';
import { useTenantOptions } from '../../hooks/useTenantOptions.js';
import { ModulePlaceholder } from '../modules/ModulePlaceholder.jsx';
import { Sidebar } from './Sidebar.jsx';
import { Topbar } from './Topbar.jsx';

export function AdminLayout({ session }) {
  const { activeModule, activeModuleId, modules, selectModule } = useActiveModule();
  const profile = session.profile;
  const tenantOptions = useTenantOptions(profile);
  const [activeTenantId, setActiveTenantId] = useState(tenantOptions[0]?.id);

  const activeTenant = useMemo(
    () => tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0],
    [activeTenantId, tenantOptions],
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
        <ModulePlaceholder module={activeModule} tenant={activeTenant} />
      </section>
    </main>
  );
}
