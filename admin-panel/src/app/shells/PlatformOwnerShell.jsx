import { ErrorBoundary } from '../../components/ui/index.js';
import { PLATFORM_NAV } from '../nav.js';
import { resolveNav } from './resolveNav.js';
import { ShellSidebar } from './components/ShellSidebar.jsx';
import { ShellTopbar } from './components/ShellTopbar.jsx';
import styles from './shell.module.css';

/**
 * Shell de flota para Platform Owner. Sin selector de tenant: la navegación es
 * cross-tenant (Fleet, System Health, Billing, Incidentes, DLQ flota, Runbooks,
 * Roles & ACL, Feature flags). Las vistas `platform-*` se registran en UI-006;
 * por ahora `resolveNav` omite las que aún no tienen módulo.
 *
 * @param {{
 *   profile?: object,
 *   permissions: object,
 *   modules: Array<object>,
 *   activeModule: object,
 *   activeModuleId?: string,
 *   onModuleSelect: (moduleId: string) => void,
 *   children: import('react').ReactNode,
 * }} props
 */
export function PlatformOwnerShell({
  profile,
  permissions,
  modules,
  activeModule,
  activeModuleId,
  onModuleSelect,
  children,
}) {
  const navGroups = resolveNav(PLATFORM_NAV, modules, permissions);

  return (
    <main className={styles.shell}>
      <ShellSidebar
        navGroups={navGroups}
        activeModuleId={activeModuleId}
        onModuleSelect={onModuleSelect}
        profile={profile}
      />
      <section className={styles.workspace}>
        <ShellTopbar eyebrow="Plataforma" title={activeModule.label} />
        <ErrorBoundary>{children}</ErrorBoundary>
      </section>
    </main>
  );
}
