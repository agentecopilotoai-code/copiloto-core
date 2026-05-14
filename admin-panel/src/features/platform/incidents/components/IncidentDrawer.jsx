import { Modal, StatusBadge } from '../../../../components/ui/index.js';
import { formatDateTime, KIND_LABEL, SEVERITY_TONE, STATUS_LABEL, STATUS_TONE } from '../meta.js';
import styles from '../Incidents.module.css';

/**
 * Incident detail drawer (modal). Shows the alert identity, the raw payload as
 * a key/value list and the delivery timeline `app.operator_alerts` carries
 * (created → scheduled → attempts/last_error → sent). Assignee, MTTR, comments
 * and postmortem links from the HTML reference are not modelled by the alert
 * row — deferred to a backend incident-management ticket; kept out of scope so
 * this drawer stays honest and under the LOC mandate.
 *
 * @param {{ incident: object | null, onClose: () => void }} props
 */
export function IncidentDrawer({ incident, onClose }) {
  if (!incident) return null;

  const payloadEntries = Object.entries(incident.payload || {});
  const timeline = [
    ['Detectado', formatDateTime(incident.created_at)],
    ['Programado', formatDateTime(incident.scheduled_for)],
    ['Intentos de envío', String(incident.attempts ?? 0)],
    ['Último error', incident.last_error || '—'],
    ['Notificado', formatDateTime(incident.sent_at)],
  ];

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={KIND_LABEL[incident.kind] || incident.kind}
      description={
        <span className={styles.drawerHeadMeta}>
          <StatusBadge tone={SEVERITY_TONE[incident.severity] || 'neutral'}>
            {incident.severity}
          </StatusBadge>
          <StatusBadge tone={STATUS_TONE[incident.status] || 'neutral'}>
            {STATUS_LABEL[incident.status] || incident.status}
          </StatusBadge>
          <span className={styles.muted}>
            {incident.tenant_name || 'Sistema (sin tenant)'}
          </span>
        </span>
      }
      footer={
        <div className={styles.drawerActions}>
          <button type="button" className={styles.linkButton} onClick={onClose}>
            Cerrar
          </button>
        </div>
      }
    >
      {incident.runbook ? (
        <p className={styles.drawerRunbook}>
          Runbook · <span className={styles.runbook}>{incident.runbook}</span>
        </p>
      ) : null}

      <h3 className={styles.drawerSection}>Timeline de entrega</h3>
      <dl className={styles.drawerGrid}>
        {timeline.map(([label, value]) => (
          <div key={label} className={styles.drawerRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className={styles.drawerSection}>Payload</h3>
      {payloadEntries.length > 0 ? (
        <dl className={styles.drawerGrid}>
          {payloadEntries.map(([key, value]) => (
            <div key={key} className={styles.drawerRow}>
              <dt>{key}</dt>
              <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className={styles.muted}>Sin payload adicional.</p>
      )}
    </Modal>
  );
}
