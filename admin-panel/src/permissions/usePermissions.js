import { useMemo } from 'react';

import { useOptionalTenantContext } from '../app/TenantProvider.jsx';
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
 * @param {{ profile?: object, tenant?: object, supportModeOverride?: object }} ctx
 *   `profile`: el `session.profile` del usuario autenticado.
 *   `tenant`:  el tenant activo (con `roles` o `role`).
 *   `supportModeOverride`: BUG-008 — `{ tenantId, expiresAt }` o `null`.
 *     Si está presente y matchea `tenant.id`, OR-ea con `profile.support_mode`
 *     para que el rol global aplique en el contexto del tenant. El backend
 *     valida independientemente con el cookie scoped (no es bypass).
 * @returns {{
 *   roles: string[],            // roles efectivos en el tenant activo
 *   role: string,               // rol más alto (para badges, default views)
 *   home: string,               // module id default según rol
 *   isSystemOwner: boolean,     // support_mode + owner/platform_owner
 *   can: (cap: string, mode?: 'R'|'RW') => boolean,
 *   level: (cap: string) => ('RW'|'R'|'partial'|'own_only'|null),
 * }}
 */
export function usePermissions({ profile, tenant, supportModeOverride } = {}) {
  // BUG-008 (codex P1 fix): si el caller no pasa `supportModeOverride`
  // explícito, leerlo del contexto del provider. Sin esto, TODOS los
  // callsites de usePermissions (router + 30+ componentes de módulo)
  // tendrían que recordar pasarlo cada vez — y al primero que se le
  // olvide, el platform_owner que activó support_mode ve "Sin acceso a
  // ningún módulo" en esa vista aunque la activación haya sido exitosa.
  // El context es opt-in (devuelve null fuera del provider, ej. tests
  // aislados) así que callers que pasan `supportModeOverride={...}`
  // explícito (tests existentes, casos custom) siguen funcionando igual.
  //
  // `useOptionalTenantContext?.()` tolera que el módulo esté mockeado en
  // tests sin que el mock exporte la función nueva — 45 tests existentes
  // hacen `vi.mock('.../TenantProvider.jsx', {useTenantContext: ...})`
  // sin incluir `useOptionalTenantContext`. Hacerlos explícitos es
  // tedioso; el `?.()` los mantiene verdes y solo afecta el path test.
  const ctx = useOptionalTenantContext?.();
  const effectiveOverride =
    supportModeOverride === undefined ? (ctx?.supportModeOverride ?? null) : supportModeOverride;
  return useMemo(() => {
    const roles = resolveActiveRoles({ profile, tenant, supportModeOverride: effectiveOverride });
    const role = highestRole(roles);
    // BUG-008 — `isSystemOwner` ahora considera ambas fuentes de support_mode:
    // el claim permanente del JWT o el override temporal (cookie) scoped al
    // tenant activo. Esto permite que el badge "Operando como soporte" se
    // muestre correctamente cuando el platform_owner activó el toggle.
    const overrideMatchesTenant = Boolean(
      effectiveOverride
      && tenant?.id
      && String(effectiveOverride.tenantId) === String(tenant.id),
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
  }, [profile, tenant, effectiveOverride]);
}
