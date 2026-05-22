import { useNavigate } from 'react-router-dom';

import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DashboardAlerts } from './components/DashboardAlerts.jsx';
import { DashboardKpis } from './components/DashboardKpis.jsx';
import { DashboardQuickLinks } from './components/DashboardQuickLinks.jsx';
import { useDashboardData } from './hooks/useDashboardData.js';
import styles from './Dashboard.module.css';

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Buenos días';
  if (hour < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

/**
 * UI-007.1 — Inicio · Dashboard.
 *
 * Owner/Admin entry page: week-over-week KPIs, operational alerts derived from
 * the analytics overview, and quick links to the day-to-day modules. Reads
 * `GET /v1/analytics/overview` (tenant-scoped, `tenant_analytics_router`) for
 * the current and previous 7-day windows.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/09 _ Inicio _ Dashboard.html`.
 * Intentional difference: the HTML shows a "today" appointment list, a 7-day
 * funnel and a channels panel; this view focuses on the backlog's UI-007.1
 * scope (KPIs + alerts + quick links). The funnel and appointment list have
 * their own dedicated views (Analítica / Citas del día) linked from here.
 *
 * @param {{ session: object, tenant: object }} props
 */
export function Dashboard({ session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const { current, previous, loading, error, refresh } = useDashboardData({
    session,
    tenantId: tenant?.id,
  });

  const displayName = profile?.name || profile?.given_name || 'de nuevo';

  function handleNavigate(moduleId) {
    if (tenant?.slug) navigate(`/t/${tenant.slug}/${moduleId}`);
  }

  return (
    <RequirePermission permissions={permissions} capability="analytics.tenant.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Inicio"
          title={`${greeting()}, ${displayName}`}
          description="Resumen del negocio de la última semana: indicadores con variación semanal, alertas operativas y accesos rápidos a las vistas del día a día."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
        />

        {error ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar el dashboard"
              description={error}
              action={
                <button type="button" className={styles.refreshButton} onClick={refresh}>
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : loading && !current ? (
          <Card padding="md">
            <EmptyState
              title="Cargando dashboard…"
              description="Consultando la analítica de la semana actual y la previa."
            />
          </Card>
        ) : (
          <>
            <DashboardKpis current={current} previous={previous} />
            <div className={styles.split}>
              <DashboardAlerts overview={current} onNavigate={handleNavigate} />
              <DashboardQuickLinks onNavigate={handleNavigate} />
            </div>
          </>
        )}
      </section>
    </RequirePermission>
  );
}
