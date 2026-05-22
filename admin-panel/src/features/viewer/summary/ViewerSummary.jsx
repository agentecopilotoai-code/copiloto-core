import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { DashboardKpis } from '../../owner-admin/dashboard/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { useSummaryData } from './hooks/useSummaryData.js';
import { SUMMARY_DESCRIPTION } from './summaryData.js';
import styles from './ViewerSummary.module.css';

/**
 * UI-010.1 — Viewer · Lectura · Resumen del negocio.
 *
 * Versión read-only de UI-007.1 (`Dashboard`). Reusa `useDashboardData` y el
 * componente `DashboardKpis` (que a su vez reusa `KpiCardWithDelta`) — no
 * refetchea ni reformula nada: las KPIs son las mismas que ve el Owner/Admin,
 * sólo cambia el chrome (PageHeader propio + chip de período + cero CTAs de
 * escritura) y la cubierta de permisos (`RequirePermission analytics.tenant.read`
 * en modo `R`).
 *
 * Per UI-010 criterio global: ningún botón de acción / quick link / alerta con
 * navegación se renderiza aquí. `DashboardQuickLinks` y `DashboardAlerts`
 * (que contienen botones con `onNavigate`) se omiten por completo. El
 * `ReadOnlyShell` (UI-002) ya añade el banner permanente "Modo solo lectura".
 *
 * Referencia visual: `docs/HTML DESIGN/Viewer/33 _ Lectura _ Resumen.html`.
 * Diferencias intencionales declaradas: el HTML muestra (1) una gráfica de
 * ingreso mensual de los últimos 12 meses, (2) un breakdown «Mix de servicios»
 * por categoría y (3) un breakdown «Origen de pacientes» por canal —
 * `analytics_overview` no expone series de 12 meses ni mix porcentual por
 * servicio / canal de origen, así que esos bloques se difieren (no se inventan
 * datos). Se renderiza el entregable mínimo viable del backlog ("Versión
 * read-only de UI-007.1. Reusa `KpiCardWithDelta`."): título + chip de período
 * + las KPIs reusadas del dashboard.
 *
 * @param {{ module?: object, session: object, tenant: object }} props
 */
export function ViewerSummary({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { current, previous, loading, error, periodLabel } = useSummaryData({
    session,
    tenantId: tenant?.id,
  });

  const hasTenant = Boolean(tenant?.id);

  return (
    <RequirePermission permissions={permissions} capability="analytics.tenant.read" mode="R">
      <section className={styles.page} data-module="viewer-summary">
        <PageHeader
          eyebrow="Lectura"
          title={module?.label || 'Resumen del negocio'}
          description={SUMMARY_DESCRIPTION}
          actions={
            <span className={styles.periodChip} aria-label="Período">
              {periodLabel}
            </span>
          }
        />

        {!hasTenant ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver el resumen del negocio."
            />
          </Card>
        ) : error && !current ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar el resumen"
              description={error}
            />
          </Card>
        ) : loading && !current ? (
          <Card padding="md">
            <EmptyState
              title="Cargando resumen…"
              description="Consultando la analítica de la semana actual y la previa."
            />
          </Card>
        ) : (
          <DashboardKpis current={current} previous={previous} />
        )}
      </section>
    </RequirePermission>
  );
}
