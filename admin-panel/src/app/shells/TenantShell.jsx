import { TENANT_NAV } from '../nav.js';
import { resolveNav } from './resolveNav.js';
import { ShellSidebar } from './components/ShellSidebar.jsx';
import { ShellTopbar } from './components/ShellTopbar.jsx';
import { TenantSwitcher } from './components/TenantSwitcher.jsx';
import styles from './shell.module.css';

/**
 * Shell tenant-scoped para Owner / Admin / Manager / Agent.
 *
 * Sidebar con selector de tenant + navegación agrupada filtrada por permisos.
 * El contenido del módulo activo llega por `children` (UI-003 lo reemplazará
 * por `<Outlet/>` del router).
 *
 * @param {{
 *   profile?: object,
 *   permissions: object,
 *   modules: Array<object>,
 *   activeModule: object,
 *   activeModuleId?: string,
 *   onModuleSelect: (moduleId: string) => void,
 *   tenantOptions: Array<object>,
 *   activeTenantId?: string,
 *   onTenantChange: (tenantId: string) => void,
 *   canSwitchTenants?: boolean,
 *   children: import('react').ReactNode,
 * }} props
 */
export function TenantShell({
  profile,
  permissions,
  modules,
  activeModule,
  activeModuleId,
  onModuleSelect,
  tenantOptions,
  activeTenantId,
  onTenantChange,
  canSwitchTenants = false,
  children,
}) {
  const navGroups = resolveNav(TENANT_NAV, modules, permissions);

  return (
    <main className={styles.shell}>
      <ShellSidebar
        navGroups={navGroups}
        activeModuleId={activeModuleId}
        onModuleSelect={onModuleSelect}
        profile={profile}
        tenantSwitcher={
          <TenantSwitcher
            activeTenantId={activeTenantId}
            canSwitchTenants={canSwitchTenants}
            onTenantChange={onTenantChange}
            tenantOptions={tenantOptions}
          />
        }
      />
      <section className={styles.workspace}>
        <ShellTopbar eyebrow="Tenant operations" title={activeModule.label} />
        {children}
      </section>
    </main>
  );
}
