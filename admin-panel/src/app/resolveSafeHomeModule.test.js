import { describe, expect, it } from 'vitest';

import { resolveSafeHomeModule } from './resolveSafeHomeModule.js';

/**
 * Branch `core`: sin módulos de producto instalados, `TENANT_NAV` solo
 * tiene la sección "Configuración" (tenant-setup, team, legal, audit) y
 * `VIEWER_NAV` está vacío.
 *
 * El helper sigue siendo el fallback defensivo: cuando un módulo se
 * instala sobre el core, agrega su entrada a `TENANT_NAV` y el helper la
 * prioriza para el redirect post-login.
 */

function permissionsWith(role, allowedCaps = []) {
  const allow = new Set(allowedCaps);
  return {
    role,
    can: (cap) => allow.has(cap),
  };
}

describe('resolveSafeHomeModule() — branch core', () => {
  it('cualquier rol → tenant-setup (capability null = accesible para todos)', () => {
    // En el core base sin módulos, el primer item navegable es tenant-setup
    // (sección "Configuración"). Su capability es null → cualquier rol pasa.
    expect(resolveSafeHomeModule(permissionsWith('owner', []))).toBe('tenant-setup');
    expect(resolveSafeHomeModule(permissionsWith('admin', []))).toBe('tenant-setup');
    expect(resolveSafeHomeModule(permissionsWith('manager', []))).toBe('tenant-setup');
    expect(resolveSafeHomeModule(permissionsWith('agent', []))).toBe('tenant-setup');
  });

  it('viewer → null (VIEWER_NAV vacío en core base)', () => {
    // VIEWER_NAV solo se popula cuando un módulo de producto registra
    // viewer-views. En el core no hay → no hay home válido para viewer.
    expect(resolveSafeHomeModule(permissionsWith('viewer', []))).toBeNull();
  });

  it('permissions inválido → null sin crash', () => {
    expect(resolveSafeHomeModule(null)).toBeNull();
    expect(resolveSafeHomeModule(undefined)).toBeNull();
    expect(resolveSafeHomeModule({})).toBeNull();
  });

  it('platform_owner en TENANT context NO devuelve platform-fleet (no rompe 404)', () => {
    // BUG-011: el helper protege contra devolver un módulo PLATFORM cuando
    // se invoca desde /t/{slug}/ (donde NO hay route registrada para
    // platform-fleet). En el core sin módulos, cae a tenant-setup.
    const permissions = permissionsWith('platform_owner', ['platform.tenants.read']);
    const result = resolveSafeHomeModule(permissions);
    expect(result).not.toBe('platform-fleet');
    expect(result).toBe('tenant-setup');
  });
});
