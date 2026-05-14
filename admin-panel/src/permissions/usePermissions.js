import { useMemo } from 'react';

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
 * @param {{ profile?: object, tenant?: object }} ctx
 *   `profile`: el `session.profile` del usuario autenticado.
 *   `tenant`:  el tenant activo (con `roles` o `role`).
 * @returns {{
 *   roles: string[],            // roles efectivos en el tenant activo
 *   role: string,               // rol más alto (para badges, default views)
 *   home: string,               // module id default según rol
 *   isSystemOwner: boolean,     // support_mode + owner/platform_owner
 *   can: (cap: string, mode?: 'R'|'RW') => boolean,
 *   level: (cap: string) => ('RW'|'R'|'partial'|'own_only'|null),
 * }}
 */
export function usePermissions({ profile, tenant } = {}) {
  return useMemo(() => {
    const roles = resolveActiveRoles({ profile, tenant });
    const role = highestRole(roles);
    const supportMode = Boolean(profile?.support_mode);
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
  }, [profile, tenant]);
}
