import { useMemo } from 'react';
import styles from './DataTable.module.css';
import { EmptyState } from './EmptyState.jsx';

/**
 * DataTable — semantic, responsive table with sortable columns and row actions.
 *
 * Columns shape:
 *   { key: string, header: ReactNode, accessor?: (row) => ReactNode,
 *     align?: 'left'|'right'|'center', sortable?: boolean, width?: string }
 *
 * @param {Object} props
 * @param {Array<Object>} props.columns
 * @param {Array<Object>} props.rows
 * @param {(row, index) => string|number} [props.rowKey]
 * @param {(row) => void} [props.onRowClick]
 * @param {{key: string, direction: 'asc'|'desc'}|null} [props.sort]
 * @param {(key: string) => void} [props.onSortChange]
 * @param {React.ReactNode} [props.empty] Custom empty state.
 * @param {string} [props.caption] Accessible caption.
 * @param {boolean} [props.loading=false]
 * @param {boolean} [props.dense=false]
 */
export function DataTable({
  columns,
  rows,
  rowKey,
  onRowClick,
  sort = null,
  onSortChange,
  empty,
  caption,
  loading = false,
  dense = false,
  className = '',
}) {
  const keyFor = useMemo(
    () => rowKey || ((row, idx) => row.id ?? row.key ?? idx),
    [rowKey],
  );

  if (!loading && rows.length === 0) {
    return (
      <div className={styles.emptyWrap}>
        {empty || <EmptyState title="Sin resultados" description="No hay datos para mostrar todavía." />}
      </div>
    );
  }

  const tableClasses = [styles.table, dense ? styles['table--dense'] : '', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={styles.scroll} role="region" aria-label={caption || 'Tabla de datos'}>
      <table className={tableClasses}>
        {caption ? <caption className={styles.caption}>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sort?.key === col.key;
              const ariaSort = isSorted ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none';
              return (
                <th
                  key={col.key}
                  scope="col"
                  className={styles[`align-${col.align || 'left'}`]}
                  style={col.width ? { width: col.width } : undefined}
                  aria-sort={col.sortable ? ariaSort : undefined}
                >
                  {col.sortable && onSortChange ? (
                    <button
                      type="button"
                      className={styles.sortBtn}
                      onClick={() => onSortChange(col.key)}
                    >
                      {col.header}
                      <span className={styles.sortIcon} aria-hidden="true">
                        {isSorted ? (sort.direction === 'asc' ? '▲' : '▼') : '↕'}
                      </span>
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className={styles.loadingCell}>
                Cargando…
              </td>
            </tr>
          ) : (
            rows.map((row, rowIdx) => (
              <tr
                key={keyFor(row, rowIdx)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? styles.clickable : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={styles[`align-${col.align || 'left'}`]}
                  >
                    {col.accessor ? col.accessor(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
