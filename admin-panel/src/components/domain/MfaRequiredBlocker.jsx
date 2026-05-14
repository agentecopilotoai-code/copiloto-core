import { adminPath } from '../../services/adminSession.js';

/**
 * Gate no-descartable que bloquea todo el panel cuando el servidor reporta
 * `session.mfa_required === true` (TASK-0080 / BUG14). Espejo del 403
 * `mfa_required` que el BFF devuelve para operaciones privilegiadas: ningún
 * contenido se renderiza hasta que el usuario reautentica con MFA.
 */
export function MfaRequiredBlocker() {
  return (
    <div className="mfa-required-overlay" role="alertdialog" aria-modal="true">
      <div className="mfa-required-card">
        <div className="mfa-required-icon" aria-hidden="true">🔐</div>
        <h2 className="mfa-required-title">Verificación en dos pasos obligatoria</h2>
        <p className="mfa-required-body">
          Tu sesión tiene acceso privilegiado (<strong>admin</strong> /{' '}
          <strong>owner</strong> / <strong>platform_owner</strong>) pero no se
          detectó autenticación de segundo factor (MFA). El servidor rechazará
          cualquier operación privilegiada con <code>403 mfa_required</code>
          hasta que reinicies sesión con MFA habilitado en Auth0.
        </p>
        <p className="mfa-required-hint">
          Cierra sesión y vuelve a entrar; Auth0 te pedirá el segundo factor
          configurado en tu cuenta.
        </p>
        <div className="mfa-required-actions">
          <form method="post" action={adminPath('/admin/logout')}>
            <button className="mfa-required-action" type="submit">
              Cerrar sesión
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
