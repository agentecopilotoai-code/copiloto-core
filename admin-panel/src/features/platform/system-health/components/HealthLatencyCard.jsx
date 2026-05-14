import { Card, CardHeader, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../SystemHealth.module.css';

// Latency bars are scaled against the 5s alert threshold (`alerts.yaml` →
// `BotResponseLatencyP95High`), so a full bar means "at the alerting limit".
const LATENCY_SCALE_SECONDS = 5;

function pct(value) {
  if (value === null || value === undefined) return 0;
  return Math.min((Number(value) / LATENCY_SCALE_SECONDS) * 100, 100);
}

function formatSeconds(value) {
  if (value === null || value === undefined) return '—';
  return `${Number(value).toFixed(2)} s`;
}

/**
 * Latency panel: p50 / p95 / p99 of the bot's inbound→reply latency rendered as
 * labelled bars against the 5s alert threshold. Surfaces the
 * `BotResponseLatencyP95High` alert inline when it is active.
 *
 * The HTML reference shows a time-series chart; we render a point-in-time bar
 * view instead — historical series require the Prometheus query API and are
 * deferred (declared as an intentional difference in the PR).
 *
 * @param {{ latency: object, alerts: Array<object> }} props
 */
export function HealthLatencyCard({ latency, alerts }) {
  const rows = [
    { key: 'p50', label: 'p50', value: latency?.p50 },
    { key: 'p95', label: 'p95', value: latency?.p95 },
    { key: 'p99', label: 'p99', value: latency?.p99 },
  ];
  const latencyAlert = (alerts || []).find(
    (alert) => alert.name === 'BotResponseLatencyP95High',
  );

  return (
    <Card padding="md">
      <CardHeader
        title="Latencia inbound → respuesta"
        subtitle={`p50 · p95 · p99 · ${latency?.count ?? 0} respuestas observadas`}
      />
      <div className={styles.latencyBars}>
        {rows.map((row) => (
          <div key={row.key} className={styles.latencyRow}>
            <span className={styles.latencyLabel}>{row.label}</span>
            <span className={styles.latencyTrack} aria-hidden="true">
              <span className={styles.latencyFill} style={{ width: `${pct(row.value)}%` }} />
            </span>
            <span className={styles.latencyValue}>{formatSeconds(row.value)}</span>
          </div>
        ))}
      </div>
      {latencyAlert ? (
        <p className={styles.latencyAlert}>
          <StatusBadge tone="danger">Alerta</StatusBadge>
          <span>
            {latencyAlert.name} · {latencyAlert.summary}
          </span>
        </p>
      ) : (
        <p className={styles.latencyOk}>Dentro del objetivo (&lt; 5s P95).</p>
      )}
    </Card>
  );
}
