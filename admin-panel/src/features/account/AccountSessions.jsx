import { useEffect, useMemo, useState } from 'react';

import { AlertBanner, PageHeader, useToast } from '../../components/ui/index.js';
import { useAuth } from '../../context/AuthContext.jsx';
import { listMySessions, revokeMySession } from '../../services/coreApi.js';
import styles from './Account.module.css';

/**
 * `/account/sessions` — Sesiones activas del usuario.
 *
 * Hidrata desde `GET /v1/me/sessions` que devuelve la lista REAL desde
 * `app.auth_sessions`. Cada request autenticada del API upsertea su sesión,
 * así que la lista que ve el user incluye la sesión actual del admin-panel
 * + cualquier otro cliente que llame al API con el mismo JWT.
 *
 * Si el backend devuelve vacío (e.g. la sesión actual aún no se upserteó),
 * mostramos un empty state honesto en vez de datos demo (que confundía a
 * usuarios pensando que su cuenta estaba abierta en sitios que no usaron).
 */
export function AccountSessions() {
  const { session } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useMemo(
    () => async () => {
      if (!session) return;
      setLoading(true);
      setError(null);
      try {
        const data = await listMySessions(session);
        setItems(Array.isArray(data?.items) ? data.items : []);
      } catch (err) {
        setError(err?.message || 'No se pudieron cargar las sesiones.');
        setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refresh();
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  async function onRevoke(targetId) {
    if (!session) return;
    try {
      await revokeMySession(session, targetId);
      toast.success('Sesión revocada.');
      await refresh();
    } catch (err) {
      toast.error(err?.message || 'No se pudo revocar la sesión.');
    }
  }

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · sesiones"
        title="Sesiones activas"
        description="Dispositivos donde tu cuenta tiene una sesión abierta. Si ves una que no reconoces, revócala y cambiá tu contraseña en Auth0."
      />

      {error ? (
        <AlertBanner tone="danger" title="No se pudieron cargar las sesiones">
          {error}
        </AlertBanner>
      ) : null}

      {loading && items.length === 0 ? (
        <p className={styles.hint}>Cargando sesiones…</p>
      ) : items.length === 0 ? (
        <AlertBanner tone="info" title="Sin sesiones registradas todavía">
          La sesión actual se registra automáticamente la primera vez que
          consultás esta página. Refrescá en unos segundos si no la ves.
        </AlertBanner>
      ) : (
        <div className={styles.sessionList} role="list" aria-label="Sesiones activas">
          {items.map((entry) => {
            const label = entry.device || entry.user_agent || 'Sesión sin nombre';
            const subtitle = [entry.location, entry.last_seen_at]
              .filter(Boolean)
              .join(' · ');
            return (
              <div className={styles.sessionRow} role="listitem" key={entry.id}>
                <div className={styles.sessionMeta}>
                  <span className={styles.sessionDevice}>
                    {label}
                    {entry.current ? (
                      <span className={styles.sessionCurrentChip}>esta sesión</span>
                    ) : null}
                  </span>
                  {subtitle ? (
                    <p className={styles.sessionLocation}>{subtitle}</p>
                  ) : null}
                </div>
                <div className={styles.sessionsActions}>
                  <button
                    type="button"
                    className={styles.dangerButton}
                    onClick={() => onRevoke(entry.id)}
                    disabled={entry.current}
                    aria-label={`Revocar sesión ${label}`}
                  >
                    Revocar
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
