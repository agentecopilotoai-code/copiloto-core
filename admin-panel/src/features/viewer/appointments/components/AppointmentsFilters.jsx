import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { STATUS_FILTER_OPTIONS } from '../viewerAppointmentsData.js';
import styles from '../ViewerAppointments.module.css';

/**
 * UI-010.3 — Formulario de filtros del listado Viewer + acción «Exportar CSV».
 *
 * Presentational: state + handlers vienen del hook `useViewerAppointmentsData`
 * vía props. No expone CTAs de escritura — el botón «Exportar CSV» es la única
 * acción autorizada por el spec del backlog ("solo filtros y export-to-CSV
 * opcional"). El submit del form no dispara fetch (los filtros corren en
 * cliente sobre la lista ya cargada) — `onSubmit={preventDefault}` evita una
 * recarga de página accidental si el usuario pulsa Enter.
 *
 * @param {{
 *   filters: { status: string, from: string, to: string, query: string },
 *   filteredCount: number,
 *   total: number,
 *   isBusy: boolean,
 *   tenantId: string | undefined,
 *   onChange: (key: string, value: string) => void,
 *   onReset: () => void,
 *   onExportCsv: () => void,
 * }} props
 */
export function AppointmentsFilters({
  filters,
  filteredCount,
  total,
  isBusy,
  tenantId,
  onChange,
  onReset,
  onExportCsv,
}) {
  const set = (key) => (event) => onChange(key, event.target.value);
  const canExport = !isBusy && tenantId && filteredCount > 0;

  return (
    <Card padding="md">
      <CardHeader
        title="Filtros"
        subtitle={`Mostrando ${filteredCount} de ${total} citas. Los filtros se aplican en cliente; usa «Exportar CSV» para descargar la selección actual.`}
      />
      <form
        className={styles.filterForm}
        onSubmit={(event) => event.preventDefault()}
      >
        <div className={styles.filterGrid}>
          <FormField label="Estado">
            <select value={filters.status} onChange={set('status')}>
              <option value="">Todos</option>
              {STATUS_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Desde">
            <input type="date" value={filters.from} onChange={set('from')} />
          </FormField>
          <FormField label="Hasta">
            <input type="date" value={filters.to} onChange={set('to')} />
          </FormField>
          <FormField label="Cliente">
            <input
              type="search"
              value={filters.query}
              onChange={set('query')}
              placeholder="Nombre del cliente…"
            />
          </FormField>
        </div>
        <div className={styles.filterActions}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={onReset}
            disabled={isBusy || !tenantId}
          >
            Limpiar filtros
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={onExportCsv}
            disabled={!canExport}
          >
            Exportar CSV
          </button>
        </div>
      </form>
    </Card>
  );
}
