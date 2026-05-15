import { useState } from 'react';

import { AlertBanner, PageHeader } from '../../components/ui/index.js';
import styles from './Account.module.css';
import { DEFAULT_SESSIONS } from './accountData.js';

/**
 * UI-016.7 — `/account/sessions`.
 *
 * Lista de sesiones activas y CTA de "Cerrar todas las demás sesiones". Read-only
 * mientras `GET /v1/me/sessions` no exista (UI-016.7-FU); las acciones "Revocar"
 * por fila y "Cerrar todas las demás" disparan el mismo `AlertBanner` informando
 * el estado del backend.
 */
export function AccountSessions() {
  const [notice, setNotice] = useState(null);

  const onRevoke = () => setNotice('revoke');
  const onRevokeAll = () => setNotice('revokeAll');

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · sesiones"
        title="Sesiones activas"
        description="Dispositivos donde tu cuenta tiene una sesión abierta. Si ves una que no reconoces, revócala y cambia tu contraseña en Auth0."
      />

      {notice ? (
        <AlertBanner
          tone="warning"
          title={
            notice === 'revokeAll'
              ? 'Cerrar otras sesiones queda en standby'
              : 'Revocar sesiones queda en standby'
          }
          action={
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => setNotice(null)}
            >
              Entendido
            </button>
          }
        >
          El endpoint <code>DELETE /v1/me/sessions/{'{sid}'}</code> está
          pendiente (<strong>UI-016.7-FU</strong>). Por ahora la lista es
          informativa; cuando el backend entregue revocación real esta acción
          cerrará la sesión seleccionada.
        </AlertBanner>
      ) : null}

      <div className={styles.sessionList} role="list" aria-label="Sesiones activas">
        {DEFAULT_SESSIONS.map((session) => (
          <div className={styles.sessionRow} role="listitem" key={session.id}>
            <div className={styles.sessionMeta}>
              <span className={styles.sessionDevice}>
                {session.device}
                {session.current ? (
                  <span className={styles.sessionCurrentChip}>esta sesión</span>
                ) : null}
              </span>
              <p className={styles.sessionLocation}>
                {session.location} · {session.last_seen_label}
              </p>
            </div>
            <div className={styles.sessionsActions}>
              <button
                type="button"
                className={styles.dangerButton}
                onClick={onRevoke}
                disabled={session.current}
                aria-label={`Revocar sesión ${session.device}`}
              >
                Revocar
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.formActions}>
        <button type="button" className={styles.dangerButton} onClick={onRevokeAll}>
          Cerrar todas las demás sesiones
        </button>
      </div>
    </section>
  );
}
