import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { ACTOR_TYPE_OPTIONS } from '../auditData.js';
import styles from '../AuditPanel.module.css';

/**
 * Dense audit-log filter form (action, actor type, entity type, date range,
 * limit) + the "Consultar" / "Exportar CSV" actions. Presentational — all state
 * and the query/export actions come from the `useAuditData` hook via props.
 *
 * @param {{
 *   filters: object,
 *   isBusy: boolean,
 *   tenantId: string | undefined,
 *   onChange: (filters: object) => void,
 *   onQuery: () => void,
 *   onExportCsv: () => void,
 * }} props
 */
export function AuditFilters({ filters, isBusy, tenantId, onChange, onQuery, onExportCsv }) {
  const set = (key) => (event) => onChange({ ...filters, [key]: event.target.value });

  return (
    <Card padding="md">
      <CardHeader
        title="Filtros"
        subtitle="Consulta y exporta el registro inmutable de acciones por tenant. Los filtros son acumulativos."
      />
      <form
        className={styles.filterForm}
        onSubmit={(event) => {
          event.preventDefault();
          onQuery();
        }}
      >
        <div className={styles.filterGrid}>
          <FormField label="Acción">
            <input
              type="text"
              value={filters.action}
              onChange={set('action')}
              placeholder="quote.created, contact.suppressed…"
            />
          </FormField>
          <FormField label="Tipo de actor">
            <select value={filters.actorType} onChange={set('actorType')}>
              <option value="">Todos</option>
              {ACTOR_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Tipo de entidad">
            <input
              type="text"
              value={filters.entityType}
              onChange={set('entityType')}
              placeholder="tenant, contact, quote…"
            />
          </FormField>
          <FormField label="Desde">
            <input type="datetime-local" value={filters.fromDate} onChange={set('fromDate')} />
          </FormField>
          <FormField label="Hasta">
            <input type="datetime-local" value={filters.toDate} onChange={set('toDate')} />
          </FormField>
          <FormField label="Límite">
            <input
              type="number"
              min="1"
              max="1000"
              value={filters.limit}
              onChange={set('limit')}
            />
          </FormField>
        </div>
        <div className={styles.filterActions}>
          <button
            type="submit"
            className={styles.primaryButton}
            disabled={isBusy || !tenantId}
          >
            Consultar
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isBusy || !tenantId}
            onClick={onExportCsv}
          >
            Exportar CSV
          </button>
        </div>
      </form>
    </Card>
  );
}
