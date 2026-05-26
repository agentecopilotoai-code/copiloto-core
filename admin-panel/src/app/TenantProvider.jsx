import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { useTenantOptions } from '../hooks/useTenantOptions.js';
import { highestRole } from '../permissions/index.js';
import {
  activateSupportMode as activateSupportModeForTenant,
  deactivateSupportMode as deactivateSupportModeForTenant,
  listMyTenants,
} from '../services/coreApi.js';

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

  // BUG-008 — supportModeOverride: opt-in temporal del `platform_owner`
  // para operar dentro de UN tenant ajeno. Reemplaza el workaround de
  // tener `app_metadata.support_mode=true` permanente en Auth0. La forma:
  //   { tenantId: string, expiresAt: Date | null }   → modo activo
  //   null                                            → modo inactivo
  // El cookie HTTP-only firmado vive en el browser (lo setea el endpoint
  // POST /v1/me/support-mode/{tenant_id}); este state es solo para que el
  // frontend pueda mostrar el banner persistente + ajustar permisos UI vía
  // resolveActiveRoles. La fuente de verdad sigue siendo la cookie + el
  // JWT validados server-side.
  const [supportModeOverride, setSupportModeOverride] = useState(null);

  const activateSupportMode = useCallback(
    async (tenantId, { justification } = {}) => {
      if (!tenantId) return null;
      const response = await activateSupportModeForTenant(session, tenantId, { justification });
      const expiresAt = response?.expires_at ? new Date(response.expires_at) : null;
      setSupportModeOverride({ tenantId: String(tenantId), expiresAt });
      return response;
    },
    [session],
  );

  const deactivateSupportMode = useCallback(
    async (tenantId) => {
      // Limpia el state local SIEMPRE — aunque el backend falle (cookie
      // ya revocada, network drop, etc.), el browser no debe quedar con
      // el banner "estás en support_mode" si el operator pidió salir.
      // El backend es idempotente (204 incluso sin cookie activo).
      setSupportModeOverride(null);
      try {
        await deactivateSupportModeForTenant(session, tenantId);
      } catch {
        /* best-effort — el cookie ya quedó borrado en el state local */
      }
    },
    [session],
  );

  const value = useMemo(
    () => ({
      session,
      profile,
      tenantOptions,
      tenantsLoading,
      hasTenant: tenantOptions.length > 0,
      handleTenantCreated,
      // BUG-008
      supportModeOverride,
      activateSupportMode,
      deactivateSupportMode,
    }),
    [
      session,
      profile,
      tenantOptions,
      tenantsLoading,
      handleTenantCreated,
      supportModeOverride,
      activateSupportMode,
      deactivateSupportMode,
    ],
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
 * Variante tolerante: devuelve `null` cuando el contexto NO está disponible
 * (en lugar de lanzar). Útil para componentes que pueden montarse en tests
 * aislados del provider — ej. `SupportModeBanner` rendererizado dentro de
 * `TenantShell.test.jsx` que no envuelve con `<TenantProvider>`.
 *
 * El consumer debe handlear el `null` (típicamente renderizando nada).
 */
export function useOptionalTenantContext() {
  return useContext(TenantContext);
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
