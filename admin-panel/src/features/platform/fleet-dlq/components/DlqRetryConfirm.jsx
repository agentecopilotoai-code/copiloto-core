import { Modal } from '../../../../components/ui/index.js';
import styles from '../FleetDlq.module.css';

const WINDOW_LABEL = {
  60: 'última hora',
  360: 'últimas 6 horas',
  1440: 'últimas 24 horas',
  10080: 'últimos 7 días',
};

/**
 * Bulk-retry confirmation modal. The platform owner confirms re-queuing every
 * failed outbound message of one tenant within the active window / error-code
 * filter. After the request resolves, the modal shows the outcome instead of
 * the confirm button so the action is never silently fire-and-forget.
 *
 * @param {{
 *   tenant: object | null,
 *   windowMinutes: number,
 *   errorCode: string,
 *   retrying: boolean,
 *   result: object | null,
 *   error: string | null,
 *   onConfirm: () => void,
 *   onClose: () => void,
 * }} props
 */
export function DlqRetryConfirm({
  tenant,
  windowMinutes,
  errorCode,
  retrying,
  result,
  error,
  onConfirm,
  onClose,
}) {
  if (!tenant) return null;

  const windowLabel = WINDOW_LABEL[windowMinutes] || `${windowMinutes} min`;
  const tenantName = tenant.display_name || tenant.slug;

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title="Reintentar DLQ del tenant"
      description={<span className={styles.muted}>{tenantName}</span>}
      footer={
        <div className={styles.drawerActions}>
          <button type="button" className={styles.linkButton} onClick={onClose}>
            {result ? 'Cerrar' : 'Cancelar'}
          </button>
          {!result ? (
            <button
              type="button"
              className={styles.primaryButton}
              onClick={onConfirm}
              disabled={retrying}
            >
              {retrying ? 'Reintentando…' : 'Confirmar reintento'}
            </button>
          ) : null}
        </div>
      }
    >
      {error ? (
        <p className={styles.retryError}>{error}</p>
      ) : result ? (
        <p className={styles.retryResult}>
          Se reencolaron <strong>{result.requeued}</strong> de {result.matched} mensajes
          {result.capped ? ' (límite alcanzado — pueden quedar más)' : ''}.
        </p>
      ) : (
        <p>
          Se re-encolarán los mensajes outbound fallidos de <strong>{tenantName}</strong> en
          la {windowLabel}
          {errorCode ? ` con error code ${errorCode}` : ''}. Cada mensaje vuelve a
          <code> status=queued</code> y el worker lo procesa de nuevo.
        </p>
      )}
    </Modal>
  );
}
