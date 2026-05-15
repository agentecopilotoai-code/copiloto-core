import { Modal } from '../../../../components/ui/index.js';
import { errorCodeLabel, formatDate, shortId } from '../outboundDlqData.js';
import styles from '../OutboundDLQ.module.css';

/**
 * Detail modal for a single failed DLQ message: error code/message, timestamps
 * and the raw provider payload. Reuses the `Modal` primitive; presentational.
 *
 * @param {{ item: object | null, onClose: () => void }} props
 */
export function DlqDetailModal({ item, onClose }) {
  if (!item) return null;

  const rows = [
    ['error_code', `${item.error_code} · ${errorCodeLabel(item.error_code)}`],
    ['error_message', item.error_message || '—'],
    ['failed_at', formatDate(item.failed_at)],
    ['message_type', item.message_type || '—'],
    ['body_preview', item.body_preview || '—'],
  ];

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={`Detalle del mensaje ${shortId(item.id)}`}
      description="Mensaje outbound que el event_worker no logró entregar a Meta."
    >
      <dl className={styles.detailGrid}>
        {rows.map(([label, value]) => (
          <div key={label} className={styles.detailRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <h4 className={styles.detailHeading}>payload</h4>
      <pre className={styles.payloadBlock}>{JSON.stringify(item.payload, null, 2)}</pre>
    </Modal>
  );
}
