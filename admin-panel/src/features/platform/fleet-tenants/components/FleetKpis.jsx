import { KpiTile } from '../../../../components/ui/index.js';
import styles from '../FleetTenants.module.css';

/**
 * Fleet · Tenants KPI grid. Aggregates are computed client-side from the
 * already-loaded fleet snapshot so the panel works without depending on
 * UI-006.2 (System Health) or UI-006.3 (Billing · MRR), which own the cross-
 * tenant time-series metrics.
 *
 * The HTML reference shows four tiles: Tenants activos, MRR, Mensajes 24h,
 * Incidentes abiertos. Aggregates we cannot compute from the tenant list
 * (MRR, mensajes 24h, incidentes) render with placeholder "—" + a footnote
 * naming the future task — honest about scope and consistent with the
 * design grid.
 *
 * @param {{
 *   items: Array<object>,
 *   total: number,
 * }} props
 */
export function FleetKpis({ items, total }) {
  const active = items.filter((tenant) => tenant.status === 'active').length;
  const trials = items.filter((tenant) => tenant.status === 'trial').length;
  const countries = new Set(items.map((tenant) => tenant.country_code)).size;

  return (
    <section className={styles.kpis} aria-label="Indicadores de la flota">
      <KpiTile
        label="Tenants activos"
        value={String(active)}
        footnote={`${total} en la flota · ${trials} trials`}
      />
      <KpiTile
        label="MRR consolidado"
        value="—"
        footnote="Disponible en UI-006.3 · Billing & MRR"
      />
      <KpiTile
        label="Países cubiertos"
        value={String(countries)}
        footnote="LatAm · derivado del listado actual"
      />
      <KpiTile
        label="Incidentes abiertos"
        value="—"
        footnote="Disponible en UI-006.4 · Incidentes"
      />
    </section>
  );
}
