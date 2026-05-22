import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { BranchesManager } from './BranchesManager.jsx';

/**
 * UI-007.7 — Negocio · Sedes (module entry).
 *
 * Permission-gated wrapper around `BranchesManager`. The manager itself is
 * ungated so the Tenant Setup wizard can embed it directly in its "Sedes" tab;
 * this entry adds the `branches.write` gate for the main-menu module route (the
 * backend remains the authority).
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function Branches({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();

  return (
    <RequirePermission permissions={permissions} capability="branches.write" mode="RW">
      <BranchesManager module={module} session={session} tenant={tenant} />
    </RequirePermission>
  );
}
