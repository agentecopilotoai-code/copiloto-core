import { KpiCardWithDelta } from '../../../../components/domain/index.js';
import { buildKpis } from '../dashboardData.js';
import styles from '../Dashboard.module.css';

/**
 * Dashboard KPI grid. Reuses `KpiCardWithDelta` (UI-004) — the week-over-week
 * delta is computed from the current vs previous `analytics_overview` windows.
 *
 * @param {{ current: object|null, previous: object|null }} props
 */
export function DashboardKpis({ current, previous }) {
  const kpis = buildKpis(current, previous);

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
