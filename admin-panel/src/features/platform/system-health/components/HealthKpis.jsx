import { KpiTile } from '../../../../components/ui/index.js';
import styles from '../SystemHealth.module.css';

function formatSeconds(value) {
  if (value === null || value === undefined) return '—';
  return `${Number(value).toFixed(2)} s`;
}

/**
 * System Health KPI grid. Four tiles mirroring the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/02 _ System Health.html`): response P95,
 * processed messages, outbound DLQ backlog and worker queue depth.
 *
 * All values come from the point-in-time Prometheus snapshot — no fabricated
 * rates. Tiles with no data render an honest "—".
 *
 * @param {{ snapshot: object }} props
 */
export function HealthKpis({ snapshot }) {
  const latency = snapshot?.response_latency || {};
  const messages = snapshot?.messages || {};
  const dlq = snapshot?.outbound_dlq || {};
  const workers = snapshot?.workers || [];

  const totalMessages = (messages.inbound || 0) + (messages.outbound || 0);
  const queueTotal = workers.reduce((sum, worker) => sum + (worker.queue_depth || 0), 0);
  const workerNames = workers.map((worker) => worker.worker).join(' · ') || 'sin workers activos';

  return (
    <section className={styles.kpis} aria-label="Indicadores de salud de la plataforma">
      <KpiTile
        label="Latencia respuesta P95"
        value={formatSeconds(latency.p95)}
        footnote={`objetivo < 5.0s · p50 ${formatSeconds(latency.p50)}`}
      />
      <KpiTile
        label="Mensajes procesados"
        value={String(totalMessages)}
        footnote={`${messages.inbound || 0} inbound · ${messages.outbound || 0} outbound`}
      />
      <KpiTile
        label="Outbound DLQ acumulado"
        value={String(dlq.total ?? 0)}
        footnote="mensajes en dead-letter queue (TASK-0065)"
      />
      <KpiTile
        label="Worker queue depth"
        value={String(queueTotal)}
        footnote={workerNames}
      />
    </section>
  );
}
