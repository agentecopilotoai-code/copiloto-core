import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { BillingKpis } from './components/BillingKpis.jsx';
import { BillingTenantsTable } from './components/BillingTenantsTable.jsx';
import { FailedPaymentsPanel } from './components/FailedPaymentsPanel.jsx';
import { MrrByCountryPanel } from './components/MrrByCountryPanel.jsx';
import { MrrByPlanTable } from './components/MrrByPlanTable.jsx';
import { usePlatformBilling } from './hooks/usePlatformBilling.js';
import styles from './BillingMrr.module.css';

function formatTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('es-CO', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

/**
 * UI-006.3 — Billing & MRR.
 *
 * Platform-owner view of the recurring revenue flowing through the fleet:
 * monthly-normalised MRR by currency / plan / tenant / country, 30-day churn
 * and failed payments. Reads `GET /v1/platform/billing/mrr` (router-protected
 * by `require_platform_owner` + `require_mfa_for_privileged`), which aggregates
 * the per-tenant subscription model of TASK-0075 across all tenants.
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/03 _ Billing _ MRR.html`.
 * Intentional difference: the HTML shows a 12-month MRR trend chart and
 * expansion/retention metrics; those need historical MRR snapshots the schema
 * does not store — deferred. This view renders the current snapshot.
 */
export function BillingMrr() {
  const { session, profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const { data, loading, error, refresh } = usePlatformBilling({ session });

  return (
    <RequirePermission permissions={permissions} capability="platform.billing.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Observability"
          title="Billing & MRR"
          description="Ingreso recurrente del fleet, agregado desde las suscripciones tenant→contacto de TASK-0075. MRR normalizada a mensual; los cobros fallidos vienen de las suscripciones en mora."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
          meta={
            <span className={styles.metaTime}>Snapshot: {formatTime(data?.generated_at)}</span>
          }
        />

        {error ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar Billing & MRR"
              description={error}
              action={
                <button type="button" className={styles.refreshButton} onClick={refresh}>
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : loading && !data ? (
          <Card padding="md">
            <EmptyState
              title="Cargando snapshot…"
              description="Agregando las suscripciones de la flota."
            />
          </Card>
        ) : (
          <>
            <BillingKpis data={data || {}} />
            <BillingTenantsTable tenants={data?.tenants} />
            <div className={styles.split}>
              <MrrByPlanTable plans={data?.mrr_by_plan} />
              <FailedPaymentsPanel failedPayments={data?.failed_payments} />
            </div>
            <MrrByCountryPanel countries={data?.by_country} />
            {data?.note ? <p className={styles.note}>{data.note}</p> : null}
          </>
        )}
      </section>
    </RequirePermission>
  );
}
