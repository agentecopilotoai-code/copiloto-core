/**
 * Landing pública del Core — pantalla para usuarios no autenticados.
 *
 * Branch `core`: pantalla mínima genérica con CTA de login. Los productos
 * que se instalen sobre el core pueden reemplazar esta pantalla con su
 * propia landing (TODO Fase 3 — module discovery).
 *
 * M46 — si la razón de 401 es `session_expired` (típicamente reinicio
 * del container `admin-panel` con sesiones in-memory), mostramos un
 * banner explicativo antes del CTA en lugar del subtitle genérico.
 */
import { useAuth } from '../../context/AuthContext.jsx';
import { adminPath } from '../../services/adminSession.js';
import styles from './PublicLanding.module.css';

export function PublicLanding() {
  const { unauthorizedReason } = useAuth();
  const sessionExpired = unauthorizedReason === 'session_expired';

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.title}>Copiloto Core</h1>
        {sessionExpired ? (
          <div
            className={styles.expiredBanner}
            role="status"
            aria-live="polite"
            data-testid="public-landing-session-expired"
          >
            <strong>Tu sesión expiró</strong>
            La cookie de sesión ya no es válida — probablemente el
            servidor de administración se reinició o pasaron más de
            8 horas desde tu login. Volvé a entrar con tu cuenta Auth0.
          </div>
        ) : (
          <p className={styles.subtitle}>
            Sistema operativo multi-tenant. Iniciá sesión para acceder al
            panel de administración.
          </p>
        )}
        <a
          className={styles.cta}
          href={adminPath('/admin/login')}
          data-testid="public-landing-login"
        >
          {sessionExpired ? 'Volver a iniciar sesión' : 'Iniciar sesión'}
        </a>
      </section>
    </main>
  );
}
