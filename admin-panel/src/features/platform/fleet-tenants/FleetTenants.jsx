import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Card, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { CreateTenantModal } from './components/CreateTenantModal.jsx';
import { FleetDrawer } from './components/FleetDrawer.jsx';
import { FleetFilters } from './components/FleetFilters.jsx';
import { FleetKpis } from './components/FleetKpis.jsx';
import { FleetTable } from './components/FleetTable.jsx';
import { useFleetTenants } from './hooks/useFleetTenants.js';
import styles from './FleetTenants.module.css';

/**
 * UI-006.1 — Fleet · Tenants.
 *
 * Platform-owner view of the entire tenant fleet. Reads from
 * `GET /v1/tenants` (router-protected by `require_platform_owner` +
 * `require_mfa_for_privileged`) and pivots into a tenant via the
 * "Ver como tenant" CTA, which navigates to that tenant's home (support_mode
 * — TASK-0077). Creating a new tenant routes to the existing onboarding
 * wizard so we do not fork the create flow.
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/01 _ Fleet _ Tenants.html`.
 */
export function FleetTenants() {
  const { session, profile, handleTenantCreated, activateSupportMode } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState(null);
  const [supportError, setSupportError] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);

  const { items, total, loading, error, refresh } = useFleetTenants({
    session,
    filters: { ...filters, limit: 100, offset: 0 },
  });

  async function handleSupportInto(tenant) {
    if (!tenant?.slug) return;
    setSupportError(null);
    // BUG-008 — antes solo navegábamos, lo que dejaba al user en "Sin
    // acceso a ningún módulo" si su JWT no tenía `support_mode=true`
    // permanente. Ahora activamos el toggle temporal vía endpoint
    // (cookie scoped + audit) ANTES de navegar. Si falla, mostramos el
    // error y NO navegamos — el user queda en /platform/tenants sabiendo
    // que no entró.
    try {
      await activateSupportMode(tenant.id);
    } catch (err) {
      setSupportError(
        err?.message
          || 'No se pudo activar support_mode. Tu sesión puede no tener el rol platform_owner.',
      );
      return;
    }
    handleTenantCreated?.({
      ...tenant,
      label: `${tenant.slug} · ${tenant.id}`,
    });
    setSelected(null);
    navigate(`/t/${tenant.slug}`);
  }

  return (
    <RequirePermission permissions={permissions} capability="platform.tenants.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Fleet"
          title="Fleet · Tenants"
          description={`${total} tenants en la flota · vista cross-tenant del Platform Owner. Las decisiones de capacidad y onboarding viven aquí.`}
          actions={
            <RequirePermission
              permissions={permissions}
              capability="platform.tenants.write"
              mode="RW"
              hidden
            >
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => setCreateOpen(true)}
                data-testid="fleet-create-tenant-btn"
              >
                + Nuevo tenant
              </button>
            </RequirePermission>
          }
        />

        <FleetKpis items={items} total={total} />

        {supportError ? (
          <Card padding="md">
            <p role="alert" className={styles.supportError}>
              {supportError}
            </p>
          </Card>
        ) : null}

        <Card padding="md">
          <FleetFilters filters={filters} onChange={setFilters} />
          <FleetTable
            rows={items}
            loading={loading}
            error={error}
            onSelect={setSelected}
            onRetry={refresh}
          />
        </Card>

        <FleetDrawer
          tenant={selected}
          session={session}
          onClose={() => setSelected(null)}
          onSupportInto={handleSupportInto}
        />

        {/* Modal "Crear tenant nuevo". Tras crear, refresca la tabla y
            DEJA AL USUARIO EN FLEET — no entra al tenant nuevo. Para
            operar el tenant, el platform_owner debe usar "Ver como
            tenant" (support_mode) desde el drawer. */}
        <CreateTenantModal
          session={session}
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { refresh(); }}
        />
      </section>
    </RequirePermission>
  );
}
