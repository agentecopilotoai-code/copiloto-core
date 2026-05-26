import { useParams } from 'react-router-dom';

import { useOptionalTenantContext } from '../app/TenantProvider.jsx';

/**
 * Resuelve el tenant activo derivándolo del slug del URL (`/t/:tenantSlug/...`)
 * y matcheándolo contra `tenantOptions` del `TenantProvider`.
 *
 * Devuelve el objeto completo del tenant (incluido `roles: string[]` mergeado
 * por `mapTenant` en `TenantProvider`), o `null` si:
 *   - No hay `TenantProvider` arriba (fuera del shell admin).
 *   - El URL no tiene `:tenantSlug`.
 *   - El slug del URL no matchea ningún tenant en `tenantOptions`.
 *
 * **Por qué este hook**: el "tenant activo" del shell admin no vive en el
 * `TenantContext` (que solo expone la lista de tenants disponibles) — lo
 * dicta la URL via React Router. Pero hooks como `usePermissions` necesitan
 * el tenant activo para resolver los roles. Antes había que pasarlo
 * explícitamente desde el componente que sí tenía acceso al outlet context
 * (típicamente `useOutletContext().activeTenant`). Eso obligaba a cada
 * callsite a "saber" la cadena de outlet contexts — frágil y olvidable.
 *
 * Antes los callsites tenían que pasar `usePermissions({ profile, tenant })`
 * explícito; sin esos args los roles efectivos eran `[]` y todas las CTAs
 * quedaban deshabilitadas. Este hook + el fallback en `usePermissions`
 * cierran ese gap sin tocar cada callsite.
 *
 * @returns {object|null} El tenant activo con sus roles, o `null`.
 */
export function useActiveTenant() {
  const ctx = useOptionalTenantContext();
  // `useParams` SIEMPRE se llama (rules-of-hooks): no puede ir después
  // de un return condicional. Fuera de un Route devuelve `{}`, así que
  // es seguro invocarlo siempre.
  const params = useParams();
  // Override opt-in para tests: si el `TenantContext` mock expone
  // `activeTenant`, lo usamos directamente. En runtime, el provider real
  // (`TenantProvider`) NO setea este campo (no derivar tenant aquí sería
  // un patrón fuera-del-router) — solo lo aprovechan los tests aislados
  // que mockean el context con `mockTenantContext = { activeTenant: TENANT }`
  // sin tener que envolver con `<Router>` + slug correcto.
  if (ctx && Object.prototype.hasOwnProperty.call(ctx, 'activeTenant')) {
    return ctx.activeTenant ?? null;
  }
  const tenantSlug = params?.tenantSlug;
  if (!ctx?.tenantOptions || !tenantSlug) {
    return null;
  }
  return ctx.tenantOptions.find((option) => option.slug === tenantSlug) || null;
}
