import { describe, expect, it } from 'vitest';

import { resolveSafeHomeModule } from './resolveSafeHomeModule.js';

/**
 * UI-018 — tests del fallback seguro al calcular el home post-login.
 *
 * Construimos un "permissions" mínimo con la misma forma que devuelve
 * `usePermissions()`: `{ role, can(cap, mode) }`. No usamos `renderHook`
 * porque el helper no es un hook (es una función pura) y queremos controlar
 * el set de capabilities exactamente.
 */

/**
 * Crea un mock de permissions que reporta `true` para las capabilities listadas
 * y `false` para el resto. `mode` se ignora aquí — sólo verificamos que la
 * capability esté en el allowlist; el modo real se respeta en la matriz.
 */
function permissionsWith(role, allowedCaps = []) {
  const allow = new Set(allowedCaps);
  return {
    role,
    can: (cap) => allow.has(cap),
  };
}

describe('resolveSafeHomeModule()', () => {
  it('owner con todas las caps → ROLE_HOME.owner (= dashboard)', () => {
    // Owner real: la matriz le da acceso a TODO. Como `dashboard` exige
    // `analytics.tenant.read`, lo incluimos en el allowlist y esperamos que
    // el helper devuelva el ROLE_HOME preferido sin necesidad de iterar
    // `TENANT_NAV`.
    const permissions = permissionsWith('owner', [
      'analytics.tenant.read',
      'services.read',
      'conversations.view',
    ]);
    expect(resolveSafeHomeModule(permissions)).toBe('dashboard');
  });

  it('manager-en-JWT pero solo caps de agent → cae al primer módulo accesible del nav', () => {
    // Escenario realista de UI-018: rol efectivo `manager` pero las caps
    // disponibles son las de un agent puro y NO incluyen `analytics.tenant.read`
    // (cap de `manager-analytics`, el ROLE_HOME.manager). El helper debe
    // saltarse el ROLE_HOME y devolver el primer módulo del TENANT_NAV cuya
    // cap esté en el allowlist.
    //
    // Orden del nav (ver `nav.js`):
    //   Inicio: ['dashboard', 'manager-analytics', 'onboarding-wizard']
    //   Conversaciones: ['operations-desk', 'my-handoffs', ...]
    //
    // Con `conversations.view` el primer accesible es `operations-desk`.
    const permissions = permissionsWith('manager', [
      'conversations.view',
      'appointments.view',
    ]);
    expect(resolveSafeHomeModule(permissions)).toBe('operations-desk');
  });

  it('viewer con su cap de lectura → ROLE_HOME.viewer (= viewer-summary)', () => {
    const permissions = permissionsWith('viewer', [
      'analytics.tenant.read',
      'appointments.view',
      'conversations.view',
    ]);
    expect(resolveSafeHomeModule(permissions)).toBe('viewer-summary');
  });

  it('rol viewer SIN su capability de lectura → fallback en el VIEWER_NAV, no en TENANT_NAV', () => {
    // Edge defensiva: si por alguna razón un viewer no tiene
    // `analytics.tenant.read` (el ROLE_HOME.viewer la exige), el helper debe
    // iterar `VIEWER_NAV` (no `TENANT_NAV`). Le damos `appointments.view`
    // para que `viewer-appointments` resulte accesible.
    const permissions = permissionsWith('viewer', ['appointments.view']);
    expect(resolveSafeHomeModule(permissions)).toBe('viewer-appointments');
  });

  it('rol vacío (caps = []) → null (el router debe pintar el StateScreen)', () => {
    const permissions = permissionsWith('viewer', []);
    expect(resolveSafeHomeModule(permissions)).toBeNull();
  });

  it('permissions inválido → null sin crash', () => {
    expect(resolveSafeHomeModule(null)).toBeNull();
    expect(resolveSafeHomeModule(undefined)).toBeNull();
    expect(resolveSafeHomeModule({})).toBeNull();
  });
});
