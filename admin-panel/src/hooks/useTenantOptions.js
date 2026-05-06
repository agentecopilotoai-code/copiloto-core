import { useMemo } from 'react';

export function useTenantOptions(profile) {
  return useMemo(() => {
    const tenantId = profile?.tenant_id || 'tenant-demo-local';
    const tenantSlug = profile?.tenant_slug || 'default';

    return [
      {
        id: tenantId,
        label: `${tenantSlug} · ${tenantId}`,
      },
    ];
  }, [profile?.tenant_id, profile?.tenant_slug]);
}
