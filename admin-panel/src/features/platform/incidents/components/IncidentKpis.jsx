import { KpiTile } from '../../../../components/ui/index.js';
import styles from '../Incidents.module.css';

/**
 * Incidents KPI grid. Four tiles mirroring the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html`): open incidents,
 * P1 severity, affected tenants and resolved count.
 *
 * All values come from the `summary` block the endpoint computes
 * (`platform_incidents.summarize_incidents`).
 *
 * @param {{ summary: object }} props
 */
export function IncidentKpis({ summary }) {
  const bySeverity = summary?.by_severity || {};
  const total = summary?.total ?? 0;
  const open = summary?.open ?? 0;
  const resolved = summary?.resolved ?? 0;
  const affected = summary?.affected_tenants ?? 0;

  return (
    <section className={styles.kpis} aria-label="Indicadores de incidentes">
      <KpiTile
        label="Incidentes abiertos"
        value={String(open)}
        footnote={`${total} en el feed · ${resolved} notificados`}
      />
      <KpiTile
        label="Severidad P1"
        value={String(bySeverity.P1 || 0)}
        footnote={`P2: ${bySeverity.P2 || 0} · P3: ${bySeverity.P3 || 0}`}
      />
      <KpiTile
        label="Tenants afectados"
        value={String(affected)}
        footnote="tenants distintos con un incidente"
      />
      <KpiTile
        label="Incidentes notificados"
        value={String(resolved)}
        footnote="alertas entregadas al operador"
      />
    </section>
  );
}
