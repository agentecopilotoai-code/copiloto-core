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
    // Owner real: la matriz le da acceso a TODO. BUG-117: como `dashboard`
    // ahora exige `dashboard.read` (no la genérica `analytics.tenant.read`,
    // que también la tienen viewer/agent/manager), lo incluimos en el
    // allowlist y esperamos que el helper devuelva el ROLE_HOME preferido
    // sin necesidad de iterar `TENANT_NAV`.
    const permissions = permissionsWith('owner', [
      'dashboard.read',
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

  it('BUG-011: platform_owner en TENANT context NO devuelve `platform-fleet` (404)', () => {
    // Escenario real (2026-05-17 runtime log):
    //   - platform_owner activa support_mode contra tenant `demo-taller`.
    //   - Router navega a /admin/t/demo-taller/ (sin module id).
    //   - TenantHomeRedirect llama resolveSafeHomeModule(permissions).
    //   - ROLE_HOME.platform_owner = 'platform-fleet' (PLATFORM module).
    //   - El step 1 antes devolvía 'platform-fleet' → Navigate to='platform-fleet'
    //     relativo → /admin/t/demo-taller/platform-fleet → router NO tiene route
    //     (TENANT_MODULE_IDS solo incluye TENANT_NAV) → cae en `*` → 404.
    // Fix: step 1 ahora exige que preferredHome esté en `flatNavOrder(role)`,
    // no solo que sea accesible por capability. `platform-fleet` no está en
    // TENANT_NAV (donde el platform_owner cae cuando entra a /t/{slug}/), así
    // que skip step 1 y devuelve el primer módulo TENANT accesible.
    //
    // Damos al platform_owner las caps típicas que tiene por support_mode
    // (todas las de owner+admin del tenant) Y la cap platform.tenants.read
    // (que es la que hacía que platform-fleet pasara `isModuleAccessible`).
    const permissions = permissionsWith('platform_owner', [
      'platform.tenants.read',  // permitía pasar el isModuleAccessible viejo
      // BUG-117: dashboard ahora requiere `dashboard.read` (admin/owner).
      // Damos esa cap al platform_owner en support_mode para representar el
      // escenario realista (tiene caps owner del tenant).
      'dashboard.read',
      'analytics.tenant.read',
      'conversations.view',
      'appointments.view',
      'services.read',
    ]);
    const result = resolveSafeHomeModule(permissions);
    expect(result).not.toBe('platform-fleet');
    // Como el platform_owner en TENANT context resuelve via TENANT_NAV, el
    // primer módulo del nav con cap accesible es `dashboard`
    // (Inicio > dashboard, requiere dashboard.read tras BUG-117).
    expect(result).toBe('dashboard');
  });

  it('BUG-011: platform_owner SIN caps tenant → cae a tenant-setup (módulo tenant-routable), nunca a platform-fleet', () => {
    // Edge defensivo: platform_owner sin caps tenant (solo caps platform).
    // El helper itera TENANT_NAV y devuelve el PRIMER tenant-routable
    // accesible. `tenant-setup` no requiere capability (entry con
    // capability:null en MODULE_REGISTRY), así que el iterator del step 2
    // lo encuentra primero. Lo importante: NUNCA devuelve un módulo
    // PLATFORM (que rompería con 404 bajo /t/{slug}/).
    const permissions = permissionsWith('platform_owner', [
      'platform.tenants.read', // solo cap platform, ninguna tenant
    ]);
    const result = resolveSafeHomeModule(permissions);
    expect(result).not.toBe('platform-fleet');
    // Y tampoco ningún otro módulo platform.
    const PLATFORM_MODULE_IDS = [
      'platform-fleet',
      'platform-modules-control',
      'platform-billing-mrr',
      'platform-deals',
      'platform-roles',
      'platform-postlogin-actions',
      'platform-feature-flags',
      'platform-observability',
      'platform-compliance',
    ];
    expect(PLATFORM_MODULE_IDS.includes(result)).toBe(false);
  });
});
