import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { useTenantOptions } from '../hooks/useTenantOptions.js';
import { highestRole } from '../permissions/index.js';
import { listMyTenants } from '../services/coreApi.js';

export const ACTIVE_TENANT_STORAGE_KEY = 'copilotoia.activeTenantId';

const TenantContext = createContext(null);

/**
 * Normaliza un tenant del backend (`listMyTenants`) al shape que consume la UI.
 */
function mapTenant(tenant) {
  const roles = Array.isArray(tenant.roles)
    ? tenant.roles
    : tenant.role
      ? [tenant.role]
      : [];
  const role = tenant.role || highestRole(roles);
  return {
    id: tenant.id,
    slug: tenant.slug,
    display_name: tenant.display_name,
    roles,
    role,
    is_default: Boolean(tenant.is_default),
    label: `${tenant.slug || tenant.display_name || 'tenant'} · ${role || 'viewer'}`,
  };
}

/**
 * Provee la lista de tenants del usuario autenticado al árbol del router.
 *
 * Sustituye al estado que vivía dentro del antiguo `AdminLayout`: arranca con
 * la semilla síncrona de `useTenantOptions(profile)` y la reemplaza por la
 * respuesta real de `listMyTenants`. El tenant activo NO vive aquí — lo dicta
 * la URL (`/t/:tenantSlug`); este provider solo expone la lista + el estado de
 * carga para que el router resuelva el slug.
 *
 * @param {{ session: object, children: import('react').ReactNode }} props
 */
export function TenantProvider({ session, children }) {
  const profile = session?.profile;
  const seed = useTenantOptions(profile);
  const [tenantOptions, setTenantOptions] = useState(seed);
  const [tenantsLoading, setTenantsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setTenantsLoading(true);

    listMyTenants(session)
      .then((tenants) => {
        if (!mounted) return;
        if (Array.isArray(tenants) && tenants.length) {
          setTenantOptions(tenants.map(mapTenant));
        }
      })
      .catch(() => {
        // Sin tenant todavía: se conserva la semilla (posiblemente vacía) y el
        // router enruta a `/no-tenant`.
      })
      .finally(() => {
        if (mounted) setTenantsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [session]);

  const handleTenantCreated = useCallback((createdTenant) => {
    setTenantOptions((current) => {
      const next = {
        ...createdTenant,
        label: createdTenant.label || `${createdTenant.slug} · ${createdTenant.id}`,
      };
      if (current.some((option) => option.id === createdTenant.id)) {
        return current.map((option) => (option.id === createdTenant.id ? next : option));
      }
      return [...current, next];
    });
  }, []);

  const value = useMemo(
    () => ({
      session,
      profile,
      tenantOptions,
      tenantsLoading,
      hasTenant: tenantOptions.length > 0,
      handleTenantCreated,
    }),
    [session, profile, tenantOptions, tenantsLoading, handleTenantCreated],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

/**
 * Acceso al contexto de tenants. Lanza si se usa fuera de `<TenantProvider>`.
 */
export function useTenantContext() {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error('useTenantContext debe usarse dentro de <TenantProvider>');
  }
  return ctx;
}

/**
 * Elige el tenant por defecto para el redirect raíz `/`:
 * último tenant visitado (localStorage) → `is_default` → primero de la lista.
 */
export function pickDefaultTenant(tenantOptions) {
  if (!tenantOptions.length) return null;
  try {
    const stored = window.localStorage?.getItem(ACTIVE_TENANT_STORAGE_KEY);
    if (stored) {
      const match = tenantOptions.find((option) => option.id === stored);
      if (match) return match;
    }
  } catch {
    /* ignore storage errors */
  }
  return tenantOptions.find((option) => option.is_default) || tenantOptions[0];
}
