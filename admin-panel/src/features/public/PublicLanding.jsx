/**
 * Landing pública del Core — pantalla para usuarios no autenticados.
 *
 * Branch `core`: pantalla mínima genérica con CTA de login. Los productos
 * que se instalen sobre el core pueden reemplazar esta pantalla con su
 * propia landing (TODO Fase 3 — module discovery).
 *
 * Tipos de banner según el motivo de "no autenticado":
 *   - session_expired (M46) → cookie de sesión zombie tras reinicio del
 *     container o TTL >8h. Banner ámbar "Tu sesión expiró".
 *   - login_error=state_* (M56) → flow OAuth interrumpido (state cookie
 *     missing/mismatch/expired). Banner ámbar "El flujo de login expiró".
 *   - login_error=auth0_access_denied → user canceló en Auth0.
 *   - login_error=missing_params → callback alcanzado sin code/state
 *     (usualmente refresh manual del URL del callback).
 *
 * Default: subtitle genérico + CTA "Iniciar sesión".
 */
import { useAuth } from '../../context/AuthContext.jsx';
import { adminPath } from '../../services/adminSession.js';
import styles from './PublicLanding.module.css';

const LOGIN_ERROR_MESSAGES = {
  state_missing: {
    title: 'El flujo de login expiró',
    body:
      'Probablemente recargaste el URL de callback o pasaron varios minutos. ' +
      'Volvé a iniciar el login desde el botón de abajo.',
  },
  state_mismatch: {
    title: 'El flujo de login se confundió',
    body:
      'Esto suele pasar si abriste varias pestañas haciendo login al mismo ' +
      'tiempo. Cerrá las pestañas extra y reintentá.',
  },
  state_expired: {
    title: 'El flujo de login expiró',
    body:
      'Tardaste más de 10 minutos en completar el login en Auth0. ' +
      'Reintentá ahora.',
  },
  missing_params: {
    title: 'Callback incompleto',
    body:
      'Auth0 no devolvió todos los parámetros esperados. Reintentá ' +
      'el login desde cero.',
  },
  auth0_access_denied: {
    title: 'Cancelaste el login',
    body: 'Si querés entrar, hacé click en "Iniciar sesión" otra vez.',
  },
};

function parseLoginError() {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('login_error');
  if (!raw) return null;
  return LOGIN_ERROR_MESSAGES[raw] || {
    title: 'Hubo un problema con el login',
    body: `Error reportado por el backend: ${raw}. Reintentá ahora.`,
  };
}

export function PublicLanding() {
  const { unauthorizedReason } = useAuth();
  const sessionExpired = unauthorizedReason === 'session_expired';
  const loginError = parseLoginError();
  // El banner de login_error tiene prioridad sobre session_expired —
  // si el user acaba de fallar el OAuth, ese es el contexto reciente.
  const banner = loginError
    ? loginError
    : sessionExpired
      ? {
          title: 'Tu sesión expiró',
          body:
            'La cookie de sesión ya no es válida — probablemente el ' +
            'servidor de administración se reinició o pasaron más de ' +
            '8 horas desde tu login. Volvé a entrar con tu cuenta Auth0.',
        }
      : null;
  const ctaLabel = banner ? 'Volver a iniciar sesión' : 'Iniciar sesión';

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.title}>Copiloto Core</h1>
        {banner ? (
          <div
            className={styles.expiredBanner}
            role="status"
            aria-live="polite"
            data-testid="public-landing-session-expired"
          >
            <strong>{banner.title}</strong>
            {banner.body}
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
          {ctaLabel}
        </a>
      </section>
    </main>
  );
}
