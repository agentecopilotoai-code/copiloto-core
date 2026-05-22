import { useMemo } from 'react';

import { useOptionalTenantContext } from '../app/TenantProvider.jsx';
import { useActiveTenant } from '../hooks/useActiveTenant.js';
import {
  can as canFn,
  highestRole,
  levelFor,
  resolveActiveRoles,
  ROLE_HOME,
} from './matrix.js';

/**
 * Hook único de permisos UI. Espejo defensivo del enforcement servidor
 * (JWT + role + RLS). Toda decisión de "ocultar / deshabilitar CTA" pasa
 * por aquí — NUNCA decide accesos sensibles (los rechazará el backend con
 * 403). El hook sólo sirve para no dibujar lo que el server denegará.
 *
 * **Fuente única**: el hook lee TODO desde el context (no acepta
 * `profile`/`tenant` como argumentos). El mandato del proyecto (CLAUDE.md
 * `MANDATO IRREVOCABLE`) prohíbe paths backwards-compat — solo existe
 * UNA forma de resolver permisos:
 *
 *   - `profile` ← `useOptionalTenantContext().profile` (lo provee el
 *     `<TenantProvider session={...}>` montado en `router.jsx`).
 *   - `tenant`  ← `useActiveTenant()` (deriva del slug del URL).
 *   - `supportModeOverride` ← `useOptionalTenantContext().supportModeOverride`
 *     por default; se acepta como param SOLO para casos custom (tests
 *     aislados que necesitan simular distinto override del que está en
 *     el context).
 *
 * Tests aislados que necesiten profile/tenant distinto deben mockear
 * `useTenantContext` y `useActiveTenant` con `vi.mock(...)`, no pasar
 * args al hook.
 *
 * @param {{ supportModeOverride?: object }} [overrides]
 * @returns {{
 *   roles: string[],            // roles efectivos en el tenant activo
 *   role: string,               // rol más alto (para badges, default views)
 *   home: string,               // module id default según rol
 *   isSystemOwner: boolean,     // support_mode + owner/platform_owner
 *   can: (cap: string, mode?: 'R'|'RW') => boolean,
 *   level: (cap: string) => ('RW'|'R'|'partial'|'own_only'|null),
 * }}
 */
/**
 * Función pura: computa el mismo shape que devuelve `usePermissions`,
 * pero recibiendo `profile`/`tenant`/`supportModeOverride` como args.
 *
 * Útil en casos donde necesitamos evaluar permisos en un tenant DISTINTO
 * al activo del URL (ej. `IndexRedirect` que evalúa el safe home del
 * `defaultTenant` antes de redirigir). Esos casos NO pueden usar
 * `usePermissions()` porque el hook está atado al tenant del URL via
 * `useActiveTenant()`.
 *
 * No es un hook (no llama hooks internos), así que se puede invocar
 * múltiples veces, en condicionales, etc. Sin embargo el resultado NO
 * está memoizado — el caller lo memoiza si lo necesita.
 */
export function computePermissions({ profile, tenant, supportModeOverride } = {}) {
  const roles = resolveActiveRoles({ profile, tenant, supportModeOverride });
  const role = highestRole(roles);
  const overrideMatchesTenant = Boolean(
    supportModeOverride
    && tenant?.id
    && String(supportModeOverride.tenantId) === String(tenant.id),
  );
  const supportMode = Boolean(profile?.support_mode) || overrideMatchesTenant;
  const isSystemOwner =
    supportMode &&
    Array.isArray(profile?.roles) &&
    profile.roles.some((r) => r === 'owner' || r === 'platform_owner');
  return {
    roles,
    role,
    home: ROLE_HOME[role] || ROLE_HOME.viewer,
    isSystemOwner,
    can: (cap, mode = 'R') => canFn(roles, cap, mode),
    level: (cap) => levelFor(roles, cap),
  };
}

export function usePermissions({ supportModeOverride } = {}) {
  // `useOptionalTenantContext?.()` tolera que el módulo esté mockeado en
  // tests sin que el mock exporte la función nueva — 45 tests existentes
  // hacen `vi.mock('.../TenantProvider.jsx', {useTenantContext: ...})`
  // sin incluir `useOptionalTenantContext`. El `?.()` los mantiene verdes.
  const ctx = useOptionalTenantContext?.();
  const profile = ctx?.profile ?? null;
  const tenant = useActiveTenant?.() ?? null;
  // BUG-008 — el override permite override per-call (tests, casos custom);
  // si no se pasa, se toma del context. Diferente a profile/tenant que
  // NO se aceptan como args (single source: context).
  const effectiveOverride =
    supportModeOverride === undefined ? (ctx?.supportModeOverride ?? null) : supportModeOverride;

  return useMemo(
    () => computePermissions({
      profile,
      tenant,
      supportModeOverride: effectiveOverride,
    }),
    [profile, tenant, effectiveOverride],
  );
}
