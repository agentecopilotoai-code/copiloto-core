import { useEffect, useState } from 'react';

import { AlertBanner, PageHeader, useToast } from '../../components/ui/index.js';
import { useAuth } from '../../context/AuthContext.jsx';
import { listMySessions, revokeMySession } from '../../services/coreApi.js';
import styles from './Account.module.css';
import { DEFAULT_SESSIONS } from './accountData.js';

/**
 * UI-016.7 — `/account/sessions`.
 *
 * Lista de sesiones activas y CTA de "Cerrar todas las demás sesiones".
 *
 * UI-016.7-FU dejó GET/DELETE `/v1/me/sessions/*` como STUBS (declarado
 * follow-up `UI-016.7-FU-SESSIONS`): el backend Auth0 BFF no mantiene una
 * `app.auth_sessions` table — los JWTs son stateless y la cookie de sesión
 * vive en Auth0. GET devuelve sólo la sesión actual; DELETE acepta sólo
 * `current` (cualquier otro `session_id` → 404). Mientras tanto, el frontend
 * sigue mostrando las DEFAULT_SESSIONS demo y el `AlertBanner` explicando
 * el FU para revocaciones de "otras" sesiones.
 *
 * Cuando UI-016.7-FU-SESSIONS aterrize basta con cambiar el `useEffect` para
 * consumir `data.sessions` en lugar de `DEFAULT_SESSIONS` y quitar el banner.
 */
export function AccountSessions() {
  const { session } = useAuth();
  const toast = useToast();
  const [notice, setNotice] = useState(null);

  // UI-016.7-FU: tocamos el GET para que el backend tenga oportunidad de
  // refrescar `users.last_login_at` y para confirmar que la sesión sigue
  // viva. La respuesta hoy es informativa (no la pintamos) — esa parte la
  // completa UI-016.7-FU-SESSIONS.
  useEffect(() => {
    if (!session) return undefined;
    let cancelled = false;
    (async () => {
      try {
        await listMySessions(session);
      } catch {
        // Stub backend; ignorable en este momento.
      }
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [session]);

  async function onRevoke(targetId) {
    // El backend sólo conoce `current`; cualquier otro id da 404. Para esos
    // mostramos el AlertBanner informativo (mismo patrón que pre-FU).
    if (targetId !== 'current') {
      setNotice('revoke');
      return;
    }
    if (!session) return;
    try {
      await revokeMySession(session, 'current');
      toast.success('Sesión cerrada. Saliendo…');
    } catch (err) {
      toast.error(err?.message || 'No se pudo cerrar la sesión.');
    }
  }

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
          Por ahora solo podés cerrar la sesión actual desde acá. Para revocar
          otras sesiones activas, cambiá tu contraseña — eso invalida todos
          los inicios de sesión existentes en cualquier dispositivo.
        </AlertBanner>
      ) : null}

      <div className={styles.sessionList} role="list" aria-label="Sesiones activas">
        {DEFAULT_SESSIONS.map((entry) => (
          <div className={styles.sessionRow} role="listitem" key={entry.id}>
            <div className={styles.sessionMeta}>
              <span className={styles.sessionDevice}>
                {entry.device}
                {entry.current ? (
                  <span className={styles.sessionCurrentChip}>esta sesión</span>
                ) : null}
              </span>
              <p className={styles.sessionLocation}>
                {entry.location} · {entry.last_seen_label}
              </p>
            </div>
            <div className={styles.sessionsActions}>
              <button
                type="button"
                className={styles.dangerButton}
                onClick={() => onRevoke(entry.current ? 'current' : entry.id)}
                disabled={entry.current}
                aria-label={`Revocar sesión ${entry.device}`}
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
