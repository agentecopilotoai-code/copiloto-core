import { Card, EmptyState, PageHeader, StatusBadge } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { HealthAlerts } from './components/HealthAlerts.jsx';
import { HealthBreakers } from './components/HealthBreakers.jsx';
import { HealthKpis } from './components/HealthKpis.jsx';
import { HealthLatencyCard } from './components/HealthLatencyCard.jsx';
import { HealthServicesTable } from './components/HealthServicesTable.jsx';
import { useSystemHealth } from './hooks/useSystemHealth.js';
import styles from './SystemHealth.module.css';

function formatTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('es-CO', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '—';
  }
}

/**
 * UI-006.2 — System Health.
 *
 * Platform-owner live snapshot of the platform: response-latency percentiles,
 * processed-message counters, worker queue depth, provider circuit breakers,
 * per-service status and derived alerts. Reads `GET /v1/platform/metrics/health`
 * (router-protected by `require_platform_owner` + `require_mfa_for_privileged`),
 * which materialises the in-process Prometheus registry (TASK-0060).
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/02 _ System Health.html`.
 * Intentional difference: the HTML shows 24h/7d/30d time-series charts; this
 * view renders a point-in-time snapshot — historical series require the
 * Prometheus query API and are deferred.
 */
export function SystemHealth() {
  const { session, profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const { data, loading, error, refresh } = useSystemHealth({ session });

  const snapshot = data?.snapshot || null;
  const alerts = data?.alerts || [];
  const services = data?.services || [];

  return (
    <RequirePermission
      permissions={permissions}
      capability="platform.system_health.read"
      mode="R"
    >
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Observability"
          title="System Health"
          description="Estado vivo de la plataforma: API, base de datos, workers, breakers de proveedores y latencia del bot. Las métricas vienen del registry Prometheus (TASK-0060); las alertas referencian runbooks."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
          meta={
            <span className={styles.meta}>
              <StatusBadge tone={alerts.length > 0 ? 'warning' : 'success'}>
                {alerts.length > 0 ? `${alerts.length} alertas` : 'Sin alertas'}
              </StatusBadge>
              <span className={styles.metaTime}>
                Snapshot: {formatTime(data?.generated_at)}
              </span>
            </span>
          }
        />

        {error ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar System Health"
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
              description="Consultando el registry Prometheus in-process y la base de datos."
            />
          </Card>
        ) : (
          <>
            <HealthKpis snapshot={snapshot || {}} />
            <HealthLatencyCard latency={snapshot?.response_latency} alerts={alerts} />
            <div className={styles.split}>
              <HealthServicesTable services={services} />
              <HealthBreakers
                breakers={snapshot?.circuit_breakers || []}
                llmSuccessRate={snapshot?.llm_calls?.success_rate ?? null}
              />
            </div>
            <HealthAlerts alerts={alerts} />
            {data?.note ? <p className={styles.note}>{data.note}</p> : null}
          </>
        )}
      </section>
    </RequirePermission>
  );
}
