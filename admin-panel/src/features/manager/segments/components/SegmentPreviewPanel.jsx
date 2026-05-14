import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { KIND_LABELS, KIND_TONES, formatDate } from '../segmentsData.js';
import styles from '../SegmentsModule.module.css';

/**
 * Preview panel for the selected segment: the segment summary (kind, contact
 * count, last refreshed, description) plus the live preview sample fetched via
 * `previewContactSegment`. Presentational — the selected segment and the
 * preview payload come from the `useSegmentsData` hook. The summary fields and
 * the preview list mirror the legacy `SegmentsModule`.
 *
 * @param {{
 *   segment: object | null,
 *   preview: object | null,
 * }} props
 */
export function SegmentPreviewPanel({ segment, preview }) {
  if (!segment) {
    return (
      <Card padding="md">
        <EmptyState
          title="Selecciona o crea un segmento"
          description="Los segmentos permiten reutilizar reglas como destinatarios de campañas y filtros de contactos. Tu tenant ya viene con 5 segmentos preconfigurados."
        />
      </Card>
    );
  }

  return (
    <Card padding="md">
      <CardHeader
        title={segment.name}
        subtitle="Segmento"
        actions={
          <StatusBadge tone={KIND_TONES[segment.kind] || 'neutral'}>
            {KIND_LABELS[segment.kind] || segment.kind}
          </StatusBadge>
        }
      />

      <section className={styles.summaryPanel}>
        <strong>Resumen</strong>
        <ul className={styles.summaryList}>
          {segment.description ? (
            <li>
              Descripción: <strong>{segment.description}</strong>
            </li>
          ) : null}
          <li>
            Contactos: <strong>{segment.contact_count ?? 0}</strong>
          </li>
          <li>
            Refrescado: <strong>{formatDate(segment.last_refreshed_at)}</strong>
          </li>
          {segment.is_system ? (
            <li>
              <strong>Segmento del sistema</strong> · no se elimina
            </li>
          ) : null}
        </ul>
      </section>

      {preview ? (
        <section className={styles.previewPanel}>
          <strong>Muestra: {preview.contact_count} contactos</strong>
          {preview.sample?.length ? (
            <ul className={styles.previewList}>
              {preview.sample.map((contact) => (
                <li key={contact.contact_id} className={styles.previewItem}>
                  <strong>{contact.display_name || contact.phone_e164}</strong>
                  <div className={styles.hint}>
                    {contact.phone_e164} · opt-in: {contact.opt_in_status}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.hint}>Ningún contacto cumple las reglas actualmente.</p>
          )}
        </section>
      ) : (
        <p className={styles.hint}>
          Pulsa «Previsualizar» en la lista para ver una muestra de los contactos que coinciden.
        </p>
      )}
    </Card>
  );
}
