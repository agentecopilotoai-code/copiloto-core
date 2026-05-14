import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../SystemHealth.module.css';

const STATE_TONE = {
  closed: 'success',
  half_open: 'warning',
  open: 'danger',
};

const STATE_LABEL = {
  closed: 'closed',
  half_open: 'half-open',
  open: 'open',
};

/**
 * Circuit breaker panel: one card per provider with its current breaker state
 * (`cpi_circuit_breaker_state` gauge). Mirrors the "Circuit breakers" block of
 * the HTML reference. Per-provider success rates from the HTML are not modelled
 * by the metric (it only carries the state gauge), so the panel surfaces the
 * global LLM success rate as a footnote instead of fabricating per-provider %.
 *
 * @param {{ breakers: Array<object>, llmSuccessRate: number|null }} props
 */
export function HealthBreakers({ breakers, llmSuccessRate }) {
  const rate =
    llmSuccessRate === null || llmSuccessRate === undefined
      ? '—'
      : `${(llmSuccessRate * 100).toFixed(1)}%`;

  return (
    <Card padding="md">
      <CardHeader
        title="Circuit breakers"
        subtitle={`Éxito LLM agregado: ${rate}`}
      />
      {breakers && breakers.length > 0 ? (
        <ul className={styles.breakerList}>
          {breakers.map((breaker) => (
            <li key={breaker.provider} className={styles.breakerItem}>
              <span className={styles.breakerName}>{breaker.provider}</span>
              <StatusBadge tone={STATE_TONE[breaker.state] || 'neutral'}>
                {STATE_LABEL[breaker.state] || breaker.state}
              </StatusBadge>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Sin breakers reportados"
          description="Ningún proveedor ha reportado estado de circuit breaker en este proceso todavía."
        />
      )}
    </Card>
  );
}
