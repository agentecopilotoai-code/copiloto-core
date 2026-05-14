import { useMemo } from 'react';

import { highestRole } from '../permissions/index.js';

/**
 * Semilla síncrona de tenants derivada del `profile` de la sesión.
 *
 * Se usa como estado inicial de `TenantProvider` mientras `listMyTenants`
 * resuelve la lista real desde el backend. Incluye `slug` y `roles` porque el
 * router (`/t/:tenantSlug`) los necesita para resolver la URL antes de que el
 * fetch termine.
 *
 * @param {object} [profile] - `session.profile`.
 * @returns {Array<{id, slug, display_name, roles, role, is_default, label}>}
 */
export function useTenantOptions(profile) {
  return useMemo(() => {
    if (!profile?.tenant_id) {
      return [];
    }

    const slug = profile?.tenant_slug || 'tenant';
    const roles = Array.isArray(profile?.roles) ? profile.roles : [];
    const role = highestRole(roles);

    return [
      {
        id: profile.tenant_id,
        slug,
        display_name: profile?.tenant_name || slug,
        roles,
        role,
        is_default: true,
        label: `${slug} · ${role || 'viewer'}`,
      },
    ];
  }, [profile?.tenant_id, profile?.tenant_slug, profile?.tenant_name, profile?.roles]);
}
