import { Button, StateScreen } from '../ui/index.js';
import { adminPath } from '../../services/adminSession.js';

/**
 * UI-016.6 — MfaRequiredBlocker redibujado al diseño `T2 _ Estados de error
 * y bloqueos`. Gate no-descartable que bloquea TODO el panel cuando el
 * servidor reporta `session.mfa_required === true` (TASK-0080 / BUG14).
 * Espejo del 403 `mfa_required` del BFF: ningún contenido se renderiza hasta
 * que el usuario reautentica con MFA.
 *
 * El blocker usa `StateScreen` con la variante `modal` (overlay fijo + role
 * `alertdialog`) y tono `warning`. El primary action es un link a la URL de
 * enrollment de MFA en Auth0 (placeholder hasta que ops publique la URL
 * definitiva); el secundario es un formulario POST a `/admin/logout` que se
 * dispara por click del botón "Cerrar sesión" — la única acción que la
 * implementación previa permitía y que los static tests siguen exigiendo.
 */
export function MfaRequiredBlocker() {
  return (
    <>
      <form
        method="post"
        action={adminPath('/admin/logout')}
        id="mfa-blocker-logout-form"
        style={{ display: 'none' }}
      >
        <input type="hidden" name="mfa-blocker" value="1" />
      </form>
      <StateScreen
        tone="warning"
        modal
        role="alertdialog"
        icon={<ShieldIcon />}
        heading="Activa autenticación de dos factores"
        body={
          <>
            <p>
              Tu rol <strong>Owner</strong> / <strong>Admin</strong> requiere
              MFA. Tienes <strong>7 días</strong> para inscribirla. Cuando
              termines, el panel se desbloqueará automáticamente.
            </p>
            <p>
              Mientras tanto el servidor rechazará cualquier operación
              privilegiada con <code>403 mfa_required</code>.
            </p>
          </>
        }
        primary={
          <Button
            variant="primary"
            // Auth0 expone el flow de enrollment al volver a iniciar sesión.
            // Hasta que ops publique un endpoint dedicado, "Configurar MFA"
            // dispara el mismo logout (que reabre Auth0 con el reto MFA).
            onClick={() => {
              const form = document.getElementById('mfa-blocker-logout-form');
              if (form instanceof HTMLFormElement) form.submit();
            }}
          >
            Configurar MFA →
          </Button>
        }
        secondary={
          <Button
            variant="ghost"
            onClick={() => {
              const form = document.getElementById('mfa-blocker-logout-form');
              if (form instanceof HTMLFormElement) form.submit();
            }}
          >
            Cerrar sesión
          </Button>
        }
      />
    </>
  );
}

function ShieldIcon() {
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
      <path d="M12 3 4 6v6c0 5 4 8 8 9 4-1 8-4 8-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}
