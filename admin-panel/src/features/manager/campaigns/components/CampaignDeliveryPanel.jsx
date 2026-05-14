import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { buildDeliveryMetrics, formatDate, statusLabel, statusTone } from '../campaignsData.js';
import styles from '../CampaignsModule.module.css';

/**
 * Preview + delivery panel for the selected campaign: summary, delivery metric
 * bars (sent / delivered / read / failed) and the estimated-recipients preview
 * sample. Presentational — the selected campaign, the templates lookup and the
 * preview payload come from the `useCampaignsData` hook. The summary fields,
 * the metric bars and the preview list mirror the legacy `CampaignsModule`.
 *
 * @param {{
 *   campaign: object | null,
 *   templates: Array<object>,
 *   preview: object | null,
 * }} props
 */
export function CampaignDeliveryPanel({ campaign, templates, preview }) {
  if (!campaign) {
    return (
      <Card padding="md">
        <EmptyState
          title="Selecciona o crea una campaña"
          description="Las campañas envían un template aprobado a contactos que cumplen los criterios definidos. Solo se entrega a contactos con opt-in válido."
        />
      </Card>
    );
  }

  const templateName =
    templates.find((t) => t.id === campaign.template_id)?.name ||
    campaign.template_id ||
    '—';
  const metrics = buildDeliveryMetrics(campaign);

  return (
    <Card padding="md">
      <CardHeader
        title={campaign.name}
        subtitle="Campaña"
        actions={<StatusBadge tone={statusTone(campaign.status)}>{statusLabel(campaign.status)}</StatusBadge>}
      />

      <div className={styles.deliveryGrid}>
        <section className={styles.summaryPanel}>
          <strong>Resumen</strong>
          <ul className={styles.summaryList}>
            <li>
              Template: <strong>{templateName}</strong>
            </li>
            <li>
              Destinatarios estimados: <strong>{campaign.recipient_count || 0}</strong>
            </li>
            <li>
              Envío programado: <strong>{formatDate(campaign.scheduled_at)}</strong>
            </li>
            <li>
              Inicio: <strong>{formatDate(campaign.started_at)}</strong>
            </li>
            <li>
              Fin: <strong>{formatDate(campaign.completed_at)}</strong>
            </li>
          </ul>
        </section>

        <section className={styles.summaryPanel}>
          <strong>Métricas de entrega</strong>
          <div className={styles.metricList}>
            {metrics.map((row) => (
              <div key={row.key} className={styles.metricRow}>
                <div className={styles.metricHead}>
                  <span>{row.label}</span>
                  <strong>
                    {row.value} / {row.total}
                  </strong>
                </div>
                <div className={styles.metricTrack}>
                  <div
                    className={styles.metricFill}
                    data-tone={row.tone}
                    style={{ width: `${row.percent}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      {preview ? (
        <section className={styles.previewPanel}>
          <strong>Destinatarios estimados: {preview.recipient_count}</strong>
          {preview.sample?.length ? (
            <ul className={styles.previewList}>
              {preview.sample.map((contact) => (
                <li key={contact.id} className={styles.previewItem}>
                  <strong>{contact.display_name || contact.phone_e164}</strong>
                  <div className={styles.hint}>
                    {contact.phone_e164} · opt-in: {contact.opt_in_status}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.hint}>Ningún contacto coincide con los filtros.</p>
          )}
        </section>
      ) : null}
    </Card>
  );
}
