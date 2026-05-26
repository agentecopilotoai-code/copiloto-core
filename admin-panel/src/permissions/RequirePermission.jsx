import { AccessDenied } from './AccessDenied.jsx';

/**
 * Envoltorio declarativo que renderiza `children` sólo si `permissions.can(...)`.
 *
 * Defaults:
 *  - `mode='R'`        → cualquier acceso basta.
 *  - `fallback=<AccessDenied/>` → tarjeta amigable; pasar `null` para no pintar.
 *  - `hidden=false`    → si true, devuelve `null` cuando falla (útil para CTAs).
 *
 * @example
 *   <RequirePermission permissions={perms} capability="campaigns.write" mode="RW">
 *     <CampaignsModule .../>
 *   </RequirePermission>
 *
 * @example  Botón que se esconde sin error:
 *   <RequirePermission permissions={perms} capability="services.write" hidden>
 *     <button>Editar servicio</button>
 *   </RequirePermission>
 */
export function RequirePermission({
  permissions,
  capability,
  mode = 'R',
  fallback,
  hidden = false,
  children,
}) {
  // capability=null significa "siempre permitido". El check `can()` con
  // null devuelve false (fail-closed contra capabilities desconocidas),
  // así que necesitamos un short-circuit explícito acá para que módulos
  // sin capability (ej. tenant-setup en el core) no bloqueen al user.
  if (capability == null) return children;
  const allowed = permissions?.can?.(capability, mode) === true;
  if (allowed) return children;
  if (hidden) return null;
  return fallback ?? <AccessDenied capability={capability} mode={mode} />;
}
