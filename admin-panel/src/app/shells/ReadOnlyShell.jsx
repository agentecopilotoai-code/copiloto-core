import { ErrorBoundary } from '../../components/ui/index.js';
import { VIEWER_NAV } from '../nav.js';
import { resolveNav } from './resolveNav.js';
import { ShellSidebar } from './components/ShellSidebar.jsx';
import { ShellTopbar } from './components/ShellTopbar.jsx';
import { TenantSwitcher } from './components/TenantSwitcher.jsx';
import styles from './shell.module.css';

/**
 * Shell de solo lectura para el rol Viewer. Igual que `TenantShell` pero:
 *   - badge permanente "Modo lectura" en el sidebar,
 *   - banner permanente "Modo solo lectura" en el topbar,
 *   - la navegación incluye los módulos sin permiso como deshabilitados
 *     (sección "Sin acceso" del diseño Viewer).
 *
 * Las CTAs de escritura se ocultan dentro de cada feature vía `usePermissions`
 * (UI-010); este shell solo aporta el chrome read-only.
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
export function ReadOnlyShell({
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
  const navGroups = resolveNav(VIEWER_NAV, modules, permissions, { includeDenied: true });
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
        badge={
          <span className={styles.readOnlyBadge}>Acceso de solo lectura</span>
        }
      />
      <main className={styles.workspace} id="main-content" tabIndex={-1}>
        <ShellTopbar
          eyebrow="Lectura"
          title={activeModule.label}
          tenant={activeTenant}
          actions={<span className={styles.readOnlyBanner}>Modo solo lectura</span>}
        />
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
    </div>
  );
}
