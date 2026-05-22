import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { AgentPerformanceTable } from './components/AgentPerformanceTable.jsx';
import { CampaignsSummary } from './components/CampaignsSummary.jsx';
import { ConversionFunnel } from './components/ConversionFunnel.jsx';
import { ManagerKpis } from './components/ManagerKpis.jsx';
import { RANGE_PRESETS, useManagerAnalyticsData } from './hooks/useManagerAnalyticsData.js';
import styles from './ManagerAnalytics.module.css';

/**
 * UI-008.1 — Manager · Analítica ("Cómo va el negocio").
 *
 * Home dedicada del rol Manager: KPIs del negocio con variación período a
 * período, embudo de conversión por canal, rendimiento por agente y resumen de
 * campañas recientes. Lee en paralelo `GET /v1/analytics/{overview,funnel,
 * agents,campaigns}` (tenant-scoped) vía `useManagerAnalyticsData`. Gated por
 * `analytics.tenant.read`; el backend sigue siendo la autoridad.
 *
 * Referencia visual: `docs/HTML DESIGN/Manager/24 _ Analítica _ cómo va el
 * negocio.html`. Diferencias intencionales declaradas: el HTML muestra una
 * gráfica de ingreso diario apilado por canal, KPIs de "Ingreso atribuido" y
 * "CAC por canal", y una lista "Top servicios" — ninguno está expuesto por los
 * endpoints de analítica disponibles, así que se difieren (no se inventan
 * datos). Los KPIs renderizados usan campos reales de `analytics_overview`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function ManagerAnalytics({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useManagerAnalyticsData({
    session,
    tenantId: tenant?.id,
  });

  return (
    <RequirePermission permissions={permissions} capability="analytics.tenant.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Análisis"
          title={module?.label || 'Cómo va el negocio'}
          description="Resumen del negocio del período: indicadores con variación, embudo de conversión por canal, rendimiento por agente y campañas recientes."
          actions={
            <div className={styles.headerActions}>
              <label className={styles.rangeLabel}>
                Rango
                <select
                  className={styles.rangeSelect}
                  value={state.preset}
                  onChange={(event) => actions.setPreset(event.target.value)}
                >
                  {RANGE_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={styles.refreshButton}
                onClick={actions.refresh}
              >
                Actualizar
              </button>
            </div>
          }
        />

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver la analítica del negocio."
            />
          </Card>
        ) : state.error && !state.overview ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar la analítica"
              description={state.error}
              action={
                <button
                  type="button"
                  className={styles.refreshButton}
                  onClick={actions.refresh}
                >
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : state.loading && !state.overview ? (
          <Card padding="md">
            <EmptyState
              title="Cargando analítica…"
              description="Consultando overview, funnel, agentes y campañas del período."
            />
          </Card>
        ) : (
          <>
            <ManagerKpis
              overview={state.overview}
              previousOverview={state.previousOverview}
            />
            <div className={styles.split}>
              <ConversionFunnel funnel={state.funnel} />
              <CampaignsSummary campaigns={state.campaigns} />
            </div>
            <AgentPerformanceTable
              agents={state.agents}
              sortBy={state.sortBy}
              onSortChange={actions.setSortBy}
            />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
