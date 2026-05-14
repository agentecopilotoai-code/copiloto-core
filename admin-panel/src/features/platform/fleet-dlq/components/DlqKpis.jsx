import { KpiTile } from '../../../../components/ui/index.js';
import styles from '../FleetDlq.module.css';

/**
 * Fleet DLQ KPI grid. Mirrors the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/05 _ Outbound DLQ _ fleet.html`): total
 * failures in the window, affected tenants, top error code and the number of
 * distinct error codes.
 *
 * The HTML's "Auto-recuperados" tile is dropped — auto-recovery is not tracked
 * as a metric; showing a fabricated number would be dishonest.
 *
 * @param {{ summary: object, byErrorCode: Array<object>, windowMinutes: number }} props
 */
export function DlqKpis({ summary, byErrorCode, windowMinutes }) {
  const total = summary?.total ?? 0;
  const affected = summary?.affected_tenants ?? 0;
  const topError = summary?.top_error_code;
  const topCount = summary?.top_error_count ?? 0;
  const distinctCodes = (byErrorCode || []).length;
  const windowLabel = windowMinutes >= 60 ? `${windowMinutes / 60}h` : `${windowMinutes}m`;

  return (
    <section className={styles.kpis} aria-label="Indicadores del DLQ de la flota">
      <KpiTile
        label="Fallos en la ventana"
        value={String(total)}
        footnote={`mensajes outbound fallidos · últimas ${windowLabel}`}
      />
      <KpiTile
        label="Tenants afectados"
        value={String(affected)}
        footnote="tenants con al menos un fallo"
      />
      <KpiTile
        label="Top error"
        value={topError || '—'}
        footnote={topError ? `${topCount} ocurrencias` : 'sin fallos en la ventana'}
      />
      <KpiTile
        label="Códigos de error"
        value={String(distinctCodes)}
        footnote="códigos distintos en la ventana"
      />
    </section>
  );
}
