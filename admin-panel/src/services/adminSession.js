const backendOrigin = import.meta.env.VITE_ADMIN_BACKEND_ORIGIN || '';

export function adminPath(path) {
  return `${backendOrigin}${path}`;
}

/**
 * Sentinel devuelto por `fetchAdminSession` cuando el backend respondió 401.
 * Distingue dos casos para que la UI muestre el mensaje correcto:
 *   - `no_session`      → user nunca tuvo cookie (visita primera vez).
 *   - `session_expired` → cookie zombie del browser. Pasa típicamente
 *                          tras reiniciar el container `admin-panel`
 *                          (sesiones in-memory en `_sessions` dict).
 * El backend ya borró la cookie zombie con `Set-Cookie ... expires=past`
 * en el mismo 401, así que el próximo `fetchAdminSession()` ya vendrá
 * con `reason='no_session'` (la cookie desapareció del browser).
 */
export const SESSION_UNAUTHORIZED = Symbol('SESSION_UNAUTHORIZED');

export async function fetchAdminSession() {
  const response = await fetch(adminPath('/admin/api/session'), {
    credentials: 'include',
    headers: { accept: 'application/json' },
  });

  if (response.status === 401) {
    // M46 — body del 401 trae `{authenticated:false, reason:'session_expired'|'no_session'}`.
    // Fallback defensivo: si el body no es parseable (compat con
    // proxies/firewalls que devuelven HTML genérico para 401), tratar
    // como 'unknown' para que la UI muestre el banner genérico.
    let reason = 'unknown';
    try {
      const body = await response.json();
      reason = body?.reason || 'unknown';
    } catch {
      /* HTML 401 o body vacío → reason='unknown' */
    }
    return { unauthorized: SESSION_UNAUTHORIZED, reason };
  }

  if (!response.ok) {
    throw new Error('No se pudo cargar la sesión del panel administrativo.');
  }

  return response.json();
}
