import { describe, expect, it } from 'vitest';

import { computePermissions } from './usePermissions.js';

describe('computePermissions()', () => {
  it('admin gestiona configuración del tenant', () => {
    const p = computePermissions({
      profile: { roles: ['admin'] },
      tenant: { roles: ['admin'] },
    });
    expect(p.can('tenant_setup.write', 'RW')).toBe(true);
    expect(p.can('team.write', 'RW')).toBe(true);
    expect(p.can('platform.tenants.read')).toBe(false);
  });

  it('manager solo lee team', () => {
    const p = computePermissions({
      profile: { roles: ['manager'] },
      tenant: { roles: ['manager'] },
    });
    expect(p.can('team.read', 'R')).toBe(true);
    expect(p.can('team.write', 'RW')).toBe(false);
  });

  it('platform_owner con support_mode actúa como owner en cualquier tenant', () => {
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(p.isSystemOwner).toBe(true);
    expect(p.role).toBe('platform_owner');
    expect(p.can('platform.tenants.write', 'RW')).toBe(true);
    expect(p.can('tenant_setup.write', 'RW')).toBe(true);
  });

  it('platform_owner sin support_mode no escala privilegios en tenant ajeno', () => {
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(p.isSystemOwner).toBe(false);
    expect(p.can('platform.tenants.write', 'RW')).toBe(false);
  });

  it('home routea por rol más alto', () => {
    const owner = computePermissions({ profile: {}, tenant: { roles: ['owner'] } });
    expect(owner.home).toBe('tenant-setup');

    const agent = computePermissions({ profile: {}, tenant: { roles: ['agent'] } });
    expect(agent.home).toBe('tenant-setup');

    const platform = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: null,
    });
    expect(platform.home).toBe('platform-fleet');
  });

  it('sin tenant ni roles globales devuelve vacío (fail-closed)', () => {
    const p = computePermissions({ profile: {} });
    expect(p.roles).toEqual([]);
    expect(p.can('team.read')).toBe(false);
    expect(p.role).toBe('viewer');
  });

  it('platform_owner SIN support_mode sin tenant resuelve home a platform-fleet', () => {
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: null,
    });
    expect(p.role).toBe('platform_owner');
    expect(p.home).toBe('platform-fleet');
    expect(p.can('platform.tenants.write', 'RW')).toBe(true);
    expect(p.isSystemOwner).toBe(false);
  });

  it('level() retorna nivel exacto', () => {
    const admin = computePermissions({ profile: {}, tenant: { roles: ['admin'] } });
    expect(admin.level('team.write')).toBe('RW');
    expect(admin.level('team.read')).toBe('R');
    expect(admin.level('nope.nope')).toBeNull();
  });
});
