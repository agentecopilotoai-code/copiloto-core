import { useEffect, useMemo, useState } from 'react';

import { MfaRequiredBlocker } from '../components/domain/MfaRequiredBlocker.jsx';
import { useActiveModule } from '../hooks/useActiveModule.js';
import { useTenantOptions } from '../hooks/useTenantOptions.js';
import { highestRole, usePermissions } from '../permissions/index.js';
import { listMyTenants } from '../services/coreApi.js';
import { ModuleContent } from './ModuleContent.jsx';
import { PlatformOwnerShell } from './shells/PlatformOwnerShell.jsx';
import { ReadOnlyShell } from './shells/ReadOnlyShell.jsx';
import { TenantShell } from './shells/TenantShell.jsx';

const ACTIVE_TENANT_STORAGE_KEY = 'copilotoia.activeTenantId';

/**
 * Selecciona el shell de layout según el rol efectivo en el tenant activo:
 *   - `platform_owner` → `PlatformOwnerShell` (flota, sin selector de tenant).
 *   - `viewer`         → `ReadOnlyShell` (chrome de solo lectura).
 *   - resto            → `TenantShell` (Owner / Admin / Manager / Agent).
 */
export function shellForRole(role) {
  if (role === 'platform_owner') return PlatformOwnerShell;
  if (role === 'viewer') return ReadOnlyShell;
  return TenantShell;
}

/**
 * Orquestador del panel: resuelve sesión → tenant activo → permisos → shell de
 * rol, e inyecta `<ModuleContent/>` como contenido. Sustituye al antiguo
 * monolito `components/layout/AdminLayout` (switch por string + shell único).
 *
 * UI-003 reemplaza este componente por el router declarativo.
 */
export function AdminLayout({ session }) {
  const { activeModule, activeModuleId, selectModule, modules } = useActiveModule();
  const [tenantSetupInitialTab, setTenantSetupInitialTab] = useState(null);
  const profile = session.profile;

  // TASK-0080 / BUG14: gate duro cuando el servidor reporta mfa_required.
  const mfaRequired = session.mfa_required === true;

  const initialTenantOptions = useTenantOptions(profile);
  const [tenantOptions, setTenantOptions] = useState(initialTenantOptions);
  const [activeTenantId, setActiveTenantId] = useState(initialTenantOptions[0]?.id);

  useEffect(() => {
    let mounted = true;

    listMyTenants(session)
      .then((tenants) => {
        if (!mounted || !tenants.length) return;
        const nextOptions = tenants.map((tenant) => ({
          id: tenant.id,
          slug: tenant.slug,
          display_name: tenant.display_name,
          roles: tenant.roles || (tenant.role ? [tenant.role] : []),
          role: tenant.role || highestRole(tenant.roles),
          is_default: Boolean(tenant.is_default),
          label: `${tenant.slug || tenant.display_name || 'tenant'} · ${highestRole(tenant.roles) || 'viewer'}`,
        }));
        setTenantOptions(nextOptions);
        setActiveTenantId((currentTenantId) => {
          if (currentTenantId && nextOptions.some((t) => t.id === currentTenantId)) {
            return currentTenantId;
          }
          const stored = window.localStorage?.getItem(ACTIVE_TENANT_STORAGE_KEY);
          if (stored && nextOptions.some((t) => t.id === stored)) return stored;
          return nextOptions.find((t) => t.is_default)?.id || nextOptions[0]?.id;
        });
      })
      .catch(() => {
        // Sin tenant todavía: el shell rinde NoTenantOnboarding vía ModuleContent.
      });

    return () => {
      mounted = false;
    };
  }, [session]);

  useEffect(() => {
    if (!activeTenantId) return;
    try {
      window.localStorage?.setItem(ACTIVE_TENANT_STORAGE_KEY, activeTenantId);
    } catch {
      /* ignore storage errors */
    }
  }, [activeTenantId]);

  const activeTenant = useMemo(
    () => tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0],
    [activeTenantId, tenantOptions],
  );

  const permissions = usePermissions({ profile, tenant: activeTenant });
  const { isSystemOwner } = permissions;

  const canSwitchTenants = tenantOptions.length > 1 || isSystemOwner;
  const hasTenant = tenantOptions.length > 0;

  function handleTenantCreated(createdTenant) {
    setTenantOptions((currentOptions) => {
      const nextTenant = {
        ...createdTenant,
        label: createdTenant.label || `${createdTenant.slug} · ${createdTenant.id}`,
      };
      if (currentOptions.some((option) => option.id === createdTenant.id)) {
        return currentOptions.map((option) =>
          option.id === createdTenant.id ? nextTenant : option,
        );
      }
      return [...currentOptions, nextTenant];
    });
    setActiveTenantId(createdTenant.id);
  }

  function handleModuleSelect(moduleId) {
    if (moduleId === 'tenant-setup') setTenantSetupInitialTab(null);
    selectModule(moduleId);
  }

  function openTenantSetupTab(tab) {
    setTenantSetupInitialTab(tab);
    selectModule('tenant-setup');
  }

  if (mfaRequired) {
    return <MfaRequiredBlocker />;
  }

  const Shell = shellForRole(permissions.role);

  return (
    <Shell
      profile={profile}
      permissions={permissions}
      modules={modules}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={handleModuleSelect}
      tenantOptions={tenantOptions}
      activeTenantId={activeTenantId}
      onTenantChange={setActiveTenantId}
      canSwitchTenants={canSwitchTenants}
    >
      <ModuleContent
        activeModule={activeModule}
        activeModuleId={activeModuleId}
        permissions={permissions}
        session={session}
        tenant={activeTenant}
        hasTenant={hasTenant}
        tenantSetupInitialTab={tenantSetupInitialTab}
        onTenantCreated={handleTenantCreated}
        onNavigate={handleModuleSelect}
        onOpenTenantSetupTab={openTenantSetupTab}
      />
    </Shell>
  );
}
