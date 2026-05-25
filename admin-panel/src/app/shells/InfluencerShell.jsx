import { useNavigate } from 'react-router-dom';

import { AlertBanner, ErrorBoundary } from '../../components/ui/index.js';
import { SupportModeBanner } from '../../components/domain/SupportModeBanner.jsx';
import { INFLUENCER_NAV } from '../nav.js';
import { resolveNav } from './resolveNav.js';
import { ShellBottomNav } from './components/ShellBottomNav.jsx';
import { ShellSidebar } from './components/ShellSidebar.jsx';
import { ShellTopbar } from './components/ShellTopbar.jsx';
import { TenantSwitcher } from './components/TenantSwitcher.jsx';
import styles from './shell.module.css';

/**
 * UI-INFLU-002 — Shell del módulo Influencer / Ravit Studio.
 *
 * Mismo patrón que `TenantShell` (sidebar + sub-nav + topbar + workspace
 * con `<ErrorBoundary>`) pero:
 *   - Usa `INFLUENCER_NAV` en lugar de `TENANT_NAV` (vista de Ravit Studio,
 *     no la del tenant operativo).
 *   - El `data-module="influencer"` en el shell envuelve la app entera
 *     bajo este atributo, permitiendo que el CSS del módulo (UI-INFLU-001
 *     declara `--influencer-*` tokens) aplique de forma global a todo lo
 *     que viva en `/t/:tenantSlug/influencer/*`.
 *   - Si `moduleEnabled === false` (gate 404 del backend, TASK-INFLU-001),
 *     muestra un `<AlertBanner>` antes del `<Outlet/>` en lugar del módulo
 *     real. La decisión D2 dice 404 a nivel API; aquí lo traducimos a
 *     mensaje amistoso para el operador sin filtrar la existencia del
 *     feature a otros tenants.
 *
 * Forward `session` al `ShellTopbar` para que `TenantBrandLogo` pueda hacer
 * `fetchTenantMediaBlobUrl` (BUG-191 follow-up).
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
 *   session?: object,
 *   moduleEnabled?: boolean,
 *   children: import('react').ReactNode,
 * }} props
 */
export function InfluencerShell({
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
  session,
  moduleEnabled = true,
  children,
}) {
  const navGroups = resolveNav(INFLUENCER_NAV, modules, permissions);
  const activeTenant =
    tenantOptions?.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions?.[0] ?? null;
  const navigate = useNavigate();

  return (
    <div className={styles.shell} data-module="influencer">
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
        {/* BUG-008 — mismo banner que TenantShell. Un platform_owner que
            entra al sub-shell Influencer vía support_mode necesita ver
            el recordatorio + botón "Salir de support mode" igual que en
            el resto del tenant. Se auto-oculta si el override no
            corresponde al `activeTenantId` actual.
            `onExited` navega a /platform — sin esto el user queda en
            el módulo con la cookie ya removida y la página rota. */}
        <SupportModeBanner
          activeTenantId={activeTenantId}
          onExited={() => navigate('/platform')}
        />
        <ShellTopbar
          eyebrow="Ravit Studio"
          title={activeModule?.label ?? 'Ravit Studio'}
          tenant={activeTenant}
          session={session}
        />
        {moduleEnabled === false ? (
          <AlertBanner tone="warning" title="Módulo no habilitado">
            Este tenant no tiene el módulo Ravit Studio activo. Contacta a tu
            Platform Owner para solicitar la activación.
          </AlertBanner>
        ) : (
          // Mismo patrón que TenantShell — key fuerza unmount/remount del
          // ErrorBoundary al navegar entre sub-módulos influencer-* para que
          // un error capturado en una vista no persista en la siguiente.
          <ErrorBoundary key={activeModuleId}>{children}</ErrorBoundary>
        )}
      </main>
      <ShellBottomNav
        navGroups={navGroups}
        activeModuleId={activeModuleId}
        onModuleSelect={onModuleSelect}
      />
    </div>
  );
}
