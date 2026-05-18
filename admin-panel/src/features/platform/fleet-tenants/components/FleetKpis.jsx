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
 * BUG-123: la lista llega paginada (límite 100). Antes contábamos
 * `active`/`trials`/`countries` sobre `items` (la página actual) y los
 * mostrábamos como totales — undercount sistemático cuando la flota supera
 * el límite. Ahora detectamos `items.length < total` y degradamos los KPIs
 * sensibles a "—" con un footnote que aclara que el total real requiere
 * los aggregates server-side. Cuando `items.length === total` (flota chica
 * que cabe en una página), los KPIs reflejan la flota completa y mostramos
 * los counts como antes.
 *
 * @param {{
 *   items: Array<object>,
 *   total: number,
 * }} props
 */
export function FleetKpis({ items, total }) {
  const isPartial = items.length < total;
  const active = items.filter((tenant) => tenant.status === 'active').length;
  const trials = items.filter((tenant) => tenant.status === 'trial').length;
  const countries = new Set(items.map((tenant) => tenant.country_code)).size;

  return (
    <section className={styles.kpis} aria-label="Indicadores de la flota">
      <KpiTile
        label="Tenants activos"
        value={isPartial ? '—' : String(active)}
        footnote={
          isPartial
            ? `${total} en la flota · counts agregados pendientes de endpoint server-side`
            : `${total} en la flota · ${trials} trials`
        }
      />
      <KpiTile
        label="MRR consolidado"
        value="—"
        footnote="Disponible en la vista Billing & MRR"
      />
      <KpiTile
        label="Países cubiertos"
        value={isPartial ? '—' : String(countries)}
        footnote={
          isPartial
            ? 'Disponible cuando todos los tenants estén cargados (paginación activa)'
            : 'LatAm · derivado del listado completo'
        }
      />
      <KpiTile
        label="Incidentes abiertos"
        value="—"
        footnote="Disponible en la vista de Incidentes"
      />
    </section>
  );
}
