import { useMemo } from 'react';

export function useTenantOptions(profile) {
  return useMemo(() => {
    if (!profile?.tenant_id) {
      return [];
    }

    const tenantSlug = profile?.tenant_slug || 'tenant';

    return [
      {
        id: profile.tenant_id,
        label: `${tenantSlug} · ${profile.tenant_id}`,
      },
    ];
  }, [profile?.tenant_id, profile?.tenant_slug]);
}
