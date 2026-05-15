import { Button, StateScreen } from '../components/ui/index.js';
import { adminPath } from '../services/adminSession.js';

/**
 * UI-018 — pantalla terminal para el caso "el usuario está autenticado y tiene
 * tenant, pero su rol efectivo NO le da acceso a ningún módulo".
 *
 * Antes este caso aterrizaba en `ROLE_HOME[role]` y el guard interno
 * (`RequirePermission`) cortaba el render dejando una pantalla en blanco
 * ("error de autenticación" desde el punto de vista del usuario). Tras UI-018
 * el `IndexRedirect` / `TenantHomeRedirect` consultan `resolveSafeHomeModule`
 * y, cuando éste devuelve `null`, renderizan este componente.
 *
 * Diseño: `StateScreen` con tono `warning` + heading "Sin acceso a ningún
 * módulo" + cuerpo explicativo + CTA primario "Cerrar sesión" cableado al
 * form POST oculto a `/admin/logout` (mismo patrón que `MfaRequiredBlocker`
 * y `AccountShell`).
 */
export function NoModuleAccessScreen() {
  return (
    <>
      <form
        method="post"
        action={adminPath('/admin/logout')}
        id="no-module-access-logout-form"
        style={{ display: 'none' }}
      >
        <input type="hidden" name="no-module-access" value="1" />
      </form>
      <StateScreen
        tone="warning"
        heading="Sin acceso a ningún módulo"
        body={
          <p>
            Tu cuenta no tiene permisos para ver ningún módulo de este tenant.
            Contacta a la persona owner del negocio para que te asigne un rol o
            inicia sesión con otra cuenta.
          </p>
        }
        primary={
          <Button
            variant="primary"
            onClick={() => {
              const form = document.getElementById('no-module-access-logout-form');
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
