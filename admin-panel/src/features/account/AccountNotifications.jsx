import { useState } from 'react';

import { AlertBanner, PageHeader } from '../../components/ui/index.js';
import styles from './Account.module.css';
import {
  NOTIFICATION_CHANNELS,
  NOTIFICATION_EVENTS,
  initialNotificationMatrix,
  toggleNotificationChannel,
} from './accountData.js';

/**
 * UI-016.7 — `/account/notifications`.
 *
 * Matriz de notificaciones (eventos × canales). El HTML T3 muestra 6 eventos:
 * Digest diario, Handoff con SLA cercano, Cobro fallido, Cita confirmada,
 * Quality rating de WhatsApp baja, Resumen semanal de campañas. Cada uno se
 * puede toggear por email / WhatsApp / en-la-app.
 *
 * Sin persistencia hasta UI-016.7-FU: el botón "Guardar preferencias" dispara
 * un `AlertBanner tone="warning"` (mismo patrón que perfil).
 */
export function AccountNotifications() {
  const [matrix, setMatrix] = useState(initialNotificationMatrix());
  const [notice, setNotice] = useState(null);

  const onToggle = (eventId, channelId) => {
    setMatrix((current) => toggleNotificationChannel(current, eventId, channelId));
    setNotice(null);
  };

  const onSave = (event) => {
    event.preventDefault();
    setNotice('saved');
  };

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · notificaciones"
        title="Notificaciones"
        description="Elige qué eventos te llegan y por dónde. Las notificaciones in-app se ven en el header del panel; email y WhatsApp respetan el contacto configurado en tu perfil."
      />

      {notice === 'saved' ? (
        <AlertBanner
          tone="warning"
          title="Las preferencias todavía no se persisten"
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
          El endpoint <code>PATCH /v1/me/notifications</code> está pendiente
          (<strong>UI-016.7-FU</strong>). Tu selección queda visible en esta
          sesión, pero no llega al backend todavía.
        </AlertBanner>
      ) : null}

      <form onSubmit={onSave} className={styles.section}>
        <div
          role="table"
          aria-label="Matriz de notificaciones por evento y canal"
          className={styles.matrix}
        >
          {NOTIFICATION_EVENTS.map((event) => (
            <div role="row" className={styles.matrixRow} key={event.id}>
              <div className={styles.matrixRowText}>
                <span className={styles.matrixRowTitle}>{event.title}</span>
                <p className={styles.matrixRowDescription}>{event.description}</p>
              </div>
              <div className={styles.matrixChannels} role="group" aria-label={event.title}>
                {NOTIFICATION_CHANNELS.map((channel) => {
                  const checked = Boolean(matrix[event.id]?.[channel.id]);
                  return (
                    <label key={channel.id} className={styles.channelToggle}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggle(event.id, channel.id)}
                        data-event={event.id}
                        data-channel={channel.id}
                      />
                      <span>{channel.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className={styles.formActions}>
          <button type="submit" className={styles.primaryButton}>
            Guardar preferencias
          </button>
        </div>
      </form>
    </section>
  );
}
