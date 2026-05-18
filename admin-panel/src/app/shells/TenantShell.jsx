import { ErrorBoundary } from '../../components/ui/index.js';
import { SupportModeBanner } from '../../components/domain/SupportModeBanner.jsx';
import { TENANT_NAV } from '../nav.js';
import { resolveNav } from './resolveNav.js';
import { BackToPlatformButton } from './components/BackToPlatformButton.jsx';
import { ShellBottomNav } from './components/ShellBottomNav.jsx';
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
  const activeTenant =
    tenantOptions?.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions?.[0] ?? null;

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main-content">
        Saltar al contenido
      </a>
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
      <main className={styles.workspace} id="main-content" tabIndex={-1}>
        {/* BUG-008 — banner sticky cuando platform_owner opera bajo
            support_mode opt-in en ESTE tenant. El componente se auto-oculta
            si supportModeOverride.tenantId no matchea con activeTenantId. */}
        <SupportModeBanner activeTenantId={activeTenantId} />
        <ShellTopbar
          eyebrow="Tenant operations"
          title={activeModule.label}
          tenant={activeTenant}
          // BUG-015 — platform_owners que entran a un tenant (via support_mode
          // o creando uno nuevo) necesitan poder volver a la vista
          // cross-tenant `/platform`. Sin este botón quedaban "atrapados"
          // sin UI visible para regresar. `isSystemOwner` es true cuando el
          // user tiene rol global Y support_mode activo (JWT permanente o
          // cookie temporal BUG-008) — exactamente el caso de uso.
          actions={permissions?.isSystemOwner ? <BackToPlatformButton /> : null}
        />
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
      <ShellBottomNav
        navGroups={navGroups}
        activeModuleId={activeModuleId}
        onModuleSelect={onModuleSelect}
      />
    </div>
  );
}
