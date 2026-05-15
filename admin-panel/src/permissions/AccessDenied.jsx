import { Button, StateScreen } from '../components/ui/index.js';
import { adminPath } from '../services/adminSession.js';
import styles from './AccessDenied.module.css';

/**
 * UI-016.6 — AccessDenied refactor al diseño `T2 _ Estados de error y
 * bloqueos`. Pantalla mostrada cuando el usuario no tiene la capability
 * requerida en el tenant activo. NO reemplaza el 403 del servidor — sólo
 * evita que la UI pinte controles que el backend rechazará.
 *
 * Reutiliza el primitive `StateScreen` (tono "warning") para garantizar
 * layout consistente con `/no-tenant`, `MfaRequiredBlocker`, 404 y
 * `ErrorBoundary`.
 *
 * BUG-002 fix: el secondary action es SIEMPRE el form de logout. Sin esto,
 * un usuario que aterriza en AccessDenied sin permisos para volver al home
 * (rol vacío, capabilities nuevas, tenant sin acceso) queda en loop con
 * /no-tenant → onboarding → AccessDenied → / → ...  El logout garantiza
 * escape hatch desde CUALQUIER lockout.
 *
 * @param {Object} props
 * @param {string} props.capability Capability code (`services.write`, etc.).
 * @param {'R'|'RW'} [props.mode='R'] Modo de acceso evaluado.
 * @param {() => void} [props.onGoHome] Click handler para "Volver al inicio".
 *   Si se omite, el botón hace `window.location.assign('/admin/')`.
 * @param {React.ReactNode} [props.children] Slot opcional bajo el cuerpo.
 */
export function AccessDenied({ capability, mode = 'R', onGoHome, children }) {
  const goHome = onGoHome ?? (() => {
    if (typeof window !== 'undefined') {
      window.location.assign('/admin/');
    }
  });

  return (
    <StateScreen
      tone="warning"
      icon={<LockIcon />}
      heading="No tienes acceso a este módulo"
      body={
        <>
          <p>
            <span className={styles.eyebrow}>Acceso restringido</span>
          </p>
          <p>
            Tu rol actual no incluye la capability{' '}
            <code>{capability}</code> en modo{' '}
            <strong>{mode === 'RW' ? 'edición' : 'lectura'}</strong>. Pide a la
            owner que te promueva si necesitas {mode === 'RW' ? 'editar' : 'ver'}{' '}
            esta sección.
          </p>
          {children}
        </>
      }
      primary={
        <Button variant="primary" onClick={goHome}>
          Volver al inicio
        </Button>
      }
      secondary={
        <form method="post" action={adminPath('/admin/logout')} className={styles.logoutForm}>
          <Button type="submit" variant="ghost">
            Cerrar sesión
          </Button>
        </form>
      }
    />
  );
}

function LockIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 1 1 8 0v3" />
    </svg>
  );
}
