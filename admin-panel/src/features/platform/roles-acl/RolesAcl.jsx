import { useMemo, useState } from 'react';

import { KpiTile, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission, ROLES } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { AccessPolicyPanel } from './components/AccessPolicyPanel.jsx';
import { RolesAclFilters } from './components/RolesAclFilters.jsx';
import { RolesAclMatrix } from './components/RolesAclMatrix.jsx';
import { buildMatrixGroups, countCapabilitiesPerRole, ROLE_LABEL } from './rolesAclData.js';
import styles from './RolesAcl.module.css';

/**
 * UI-006.7 — Roles · ACL.
 *
 * Read-only platform-owner view of the `PERMISSIONS` matrix (UI-005) rendered
 * as a capability × role table, grouped by capability domain, with a
 * client-side capability search and the server-side access-policy panel.
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/07 _ Roles _ ACL.html`.
 * Intentional difference: the HTML mockup shows per-user role *assignments*
 * (users × tenants), which would need a cross-tenant users endpoint; the
 * backlog task (UI-006.7) asks for the `permissions/matrix.js` capability ×
 * role matrix made visible — that is what this view renders. The "modo edición"
 * toggle that would write to `app.permission_overrides` is deferred: that table
 * does not exist and is a separate backend ticket.
 */
export function RolesAcl() {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const [search, setSearch] = useState('');

  const groups = useMemo(() => buildMatrixGroups(search), [search]);
  const capabilityCounts = useMemo(() => countCapabilitiesPerRole(), []);

  return (
    <RequirePermission permissions={permissions} capability="platform.roles_acl.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Acceso"
          title="Roles & ACL"
          description="Matriz de permisos por capacidad × rol — el espejo en UI del modelo de acceso del servidor (JWT + role + RLS). Vista de solo lectura; el modo edición con overrides persistidos requiere un ticket de backend (tabla app.permission_overrides aún no existe)."
        />

        <section className={styles.kpis} aria-label="Capacidades por rol">
          {ROLES.map((role) => (
            <KpiTile
              key={role}
              label={ROLE_LABEL[role] || role}
              value={String(capabilityCounts[role] ?? 0)}
              footnote="capacidades con algún acceso"
            />
          ))}
        </section>

        <RolesAclFilters search={search} onSearchChange={setSearch} />
        <RolesAclMatrix groups={groups} />
        <AccessPolicyPanel />
      </section>
    </RequirePermission>
  );
}
