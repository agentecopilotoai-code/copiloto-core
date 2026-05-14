import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Card, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { retryPlatformOutboundDlq } from '../../../services/coreApi.js';
import { DlqByErrorCodePanel } from './components/DlqByErrorCodePanel.jsx';
import { DlqByTenantTable } from './components/DlqByTenantTable.jsx';
import { DlqFilters } from './components/DlqFilters.jsx';
import { DlqKpis } from './components/DlqKpis.jsx';
import { DlqRetryConfirm } from './components/DlqRetryConfirm.jsx';
import { usePlatformDlq } from './hooks/usePlatformDlq.js';
import styles from './FleetDlq.module.css';

/**
 * UI-006.5 — Outbound DLQ · fleet.
 *
 * Platform-owner cross-tenant view of failed outbound messages (TASK-0065),
 * aggregated by tenant and by error code. Reads `GET /v1/platform/outbound-dlq`
 * and drives the bulk-retry action via `POST /v1/platform/outbound-dlq/retry`
 * (both router-protected by `require_platform_owner` + `require_mfa_for_privileged`).
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/05 _ Outbound DLQ _ fleet.html`.
 * Intentional difference: the HTML's "Auto-recuperados" tile is dropped — auto-
 * recovery is not tracked as a metric. Retry is per-tenant with an explicit
 * confirmation (no fleet-wide "retry everything").
 */
export function FleetDlq() {
  const { session, profile, handleTenantCreated } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const navigate = useNavigate();

  const [filters, setFilters] = useState({ windowMinutes: 60 });
  const [retryTenant, setRetryTenant] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const [retryResult, setRetryResult] = useState(null);
  const [retryError, setRetryError] = useState(null);

  const { data, loading, error, refresh } = usePlatformDlq({ session, filters });

  function openRetry(tenant) {
    setRetryTenant(tenant);
    setRetryResult(null);
    setRetryError(null);
  }

  function closeRetry() {
    setRetryTenant(null);
    setRetryResult(null);
    setRetryError(null);
  }

  async function confirmRetry() {
    if (!retryTenant) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const result = await retryPlatformOutboundDlq(session, {
        tenant_id: retryTenant.tenant_id,
        error_code: filters.errorCode || null,
        window_minutes: filters.windowMinutes || 60,
      });
      setRetryResult(result);
      refresh();
    } catch (err) {
      setRetryError(err?.message || 'No se pudo reintentar el DLQ del tenant');
    } finally {
      setRetrying(false);
    }
  }

  function enterTenant(tenant) {
    if (!tenant?.slug) return;
    handleTenantCreated?.({ ...tenant, label: `${tenant.slug} · ${tenant.tenant_id}` });
    navigate(`/t/${tenant.slug}`);
  }

  return (
    <RequirePermission
      permissions={permissions}
      capability="platform.outbound_dlq.read"
      mode="R"
    >
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Operaciones"
          title="Outbound DLQ · fleet"
          description="Mensajes outbound que ningún worker pudo entregar a Meta, agregados cross-tenant por tenant y error code (TASK-0065). Cada tenant ve el detalle de sus propios mensajes en su panel."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
        />

        <DlqKpis
          summary={data?.summary || {}}
          byErrorCode={data?.by_error_code || []}
          windowMinutes={filters.windowMinutes || 60}
        />

        <Card padding="md">
          <DlqFilters filters={filters} onChange={setFilters} />
          <DlqByTenantTable
            rows={data?.by_tenant || []}
            loading={loading}
            error={error}
            permissions={permissions}
            onRetry={openRetry}
            onEnterTenant={enterTenant}
            onReload={refresh}
          />
        </Card>

        <DlqByErrorCodePanel rows={data?.by_error_code || []} />

        {data?.note ? <p className={styles.note}>{data.note}</p> : null}

        <DlqRetryConfirm
          tenant={retryTenant}
          windowMinutes={filters.windowMinutes || 60}
          errorCode={filters.errorCode || ''}
          retrying={retrying}
          result={retryResult}
          error={retryError}
          onConfirm={confirmRetry}
          onClose={closeRetry}
        />
      </section>
    </RequirePermission>
  );
}
