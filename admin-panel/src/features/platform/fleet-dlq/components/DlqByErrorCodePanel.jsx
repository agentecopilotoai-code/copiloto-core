import { Card, CardHeader, EmptyState } from '../../../../components/ui/index.js';
import styles from '../FleetDlq.module.css';

/**
 * "Distribución por error code" — failed-message counts grouped by Meta error
 * code across the fleet, with the published runbook when one maps cleanly.
 * Mirrors the HTML reference's error-code breakdown.
 *
 * @param {{ rows: Array<object> }} props
 */
export function DlqByErrorCodePanel({ rows }) {
  const items = rows || [];

  return (
    <Card padding="md">
      <CardHeader
        title="Distribución por error code"
        subtitle="Fallos agrupados por código de error de Meta"
      />
      {items.length > 0 ? (
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={item.error_code} className={styles.listItem}>
              <div className={styles.listMain}>
                <span className={styles.code}>{item.error_code}</span>
                {item.runbook ? (
                  <span className={styles.listMeta}>Runbook · {item.runbook}</span>
                ) : (
                  <span className={styles.listMeta}>sin runbook asociado</span>
                )}
              </div>
              <span className={styles.listCount}>{item.count}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Sin fallos en la ventana"
          description="Ningún mensaje outbound de la flota falló en la ventana seleccionada."
        />
      )}
    </Card>
  );
}
