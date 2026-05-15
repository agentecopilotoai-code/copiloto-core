import { useCallback, useEffect, useState } from 'react';

import { AlertBanner, PageHeader, useToast } from '../../components/ui/index.js';
import { useAuth } from '../../context/AuthContext.jsx';
import {
  getMyNotifications,
  patchMyNotifications,
} from '../../services/coreApi.js';
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
 * UI-016.7-FU cableó GET/PATCH `/v1/me/notifications`. El form arranca con
 * los defaults canónicos (`initialNotificationMatrix`) y, si el backend tiene
 * una matriz guardada, la merge encima — así un evento nuevo del catálogo
 * mantiene su default mientras los preexistentes preservan la elección del
 * usuario. PATCH manda la matriz completa (no diff). Éxito → toast `success`;
 * 4xx → AlertBanner; 5xx → toast `error`.
 */
export function AccountNotifications() {
  const { session } = useAuth();
  const toast = useToast();
  const [matrix, setMatrix] = useState(initialNotificationMatrix());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // UI-016.7-FU: hidrata con la matriz persistida en el backend. Si el GET
  // falla nos quedamos con los defaults canónicos del catálogo.
  useEffect(() => {
    let cancelled = false;
    if (!session) return undefined;
    (async () => {
      try {
        const data = await getMyNotifications(session);
        if (cancelled) return;
        const persisted = data?.notification_matrix || {};
        setMatrix((current) => {
          const next = { ...current };
          Object.entries(persisted).forEach(([eventId, channels]) => {
            next[eventId] = { ...(next[eventId] || {}), ...(channels || {}) };
          });
          return next;
        });
      } catch {
        // Mantiene los defaults canónicos.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session]);

  const onToggle = (eventId, channelId) => {
    setMatrix((current) => toggleNotificationChannel(current, eventId, channelId));
    setError(null);
  };

  const onSave = useCallback(
    async (event) => {
      event.preventDefault();
      if (saving || !session) return;
      setSaving(true);
      setError(null);
      try {
        await patchMyNotifications(session, matrix);
        toast.success('Preferencias de notificaciones guardadas.');
      } catch (err) {
        if (err?.status && err.status >= 400 && err.status < 500) {
          setError(err?.message || 'No se pudieron guardar las preferencias.');
        } else {
          toast.error(err?.message || 'Error inesperado al guardar.');
        }
      } finally {
        setSaving(false);
      }
    },
    [saving, session, matrix, toast],
  );

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · notificaciones"
        title="Notificaciones"
        description="Elige qué eventos te llegan y por dónde. Las notificaciones in-app se ven en el header del panel; email y WhatsApp respetan el contacto configurado en tu perfil."
      />

      {error ? (
        <AlertBanner
          tone="danger"
          title="No se pudieron guardar las preferencias"
          action={
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => setError(null)}
            >
              Cerrar
            </button>
          }
        >
          {error}
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
          <button type="submit" className={styles.primaryButton} disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar preferencias'}
          </button>
        </div>
      </form>
    </section>
  );
}
