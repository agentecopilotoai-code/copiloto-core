import { KpiCardWithDelta } from '../../../../components/domain/index.js';
import { buildManagerKpis } from '../managerAnalyticsData.js';
import styles from '../ManagerAnalytics.module.css';

/**
 * Fila de KPIs de la home del Manager. Reusa `KpiCardWithDelta` (UI-004): el
 * delta sale de comparar la ventana actual contra la previa de
 * `analytics_overview`. Solo se pintan KPIs respaldados por campos reales del
 * endpoint (ver `buildManagerKpis`).
 *
 * @param {{ overview: object|null, previousOverview: object|null }} props
 */
export function ManagerKpis({ overview, previousOverview }) {
  const kpis = buildManagerKpis(overview, previousOverview);

  return (
    <section className={styles.kpis} aria-label="Indicadores del negocio">
      {kpis.map((kpi) => (
        <KpiCardWithDelta
          key={kpi.key}
          label={kpi.label}
          value={kpi.value}
          current={kpi.current}
          previous={kpi.previous}
          invertTrend={kpi.invertTrend}
          footnote={kpi.footnote}
        />
      ))}
    </section>
  );
}
