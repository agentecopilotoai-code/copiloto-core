import { describe, expect, it } from 'vitest';

import {
  PERMISSIONS,
  ROLES,
  ROLE_HOME,
  can,
  highestRole,
  levelFor,
  resolveActiveRoles,
} from './matrix.js';

describe('PERMISSIONS matrix', () => {
  it('declara las 6 columnas para cada capability', () => {
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      for (const role of ROLES) {
        expect(row, `${key} sin columna ${role}`).toHaveProperty(role);
      }
    }
  });

  it('usa solo niveles válidos (RW, R, partial, own_only, null)', () => {
    const VALID = new Set(['RW', 'R', 'partial', 'own_only', null]);
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      for (const role of ROLES) {
        expect(VALID.has(row[role]), `nivel inválido en ${key}.${role}=${row[role]}`).toBe(true);
      }
    }
  });

  it('capabilities platform.* son exclusivas de platform_owner', () => {
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      if (!key.startsWith('platform.')) continue;
      expect(row.viewer, `${key} debería negar viewer`).toBeNull();
      expect(row.agent, `${key} debería negar agent`).toBeNull();
      expect(row.manager, `${key} debería negar manager`).toBeNull();
      expect(row.admin, `${key} debería negar admin`).toBeNull();
      expect(row.owner, `${key} debería negar owner`).toBeNull();
      expect(row.platform_owner, `${key} debería conceder platform_owner`).toBeTruthy();
    }
  });

  it('platform_owner NO ve capabilities transversales del tenant', () => {
    const TENANT_ONLY = ['tenant_setup.write', 'team.write'];
    for (const cap of TENANT_ONLY) {
      expect(
        PERMISSIONS[cap].platform_owner,
        `${cap} no debe ser visible a platform_owner`,
      ).toBeNull();
    }
  });
});

describe('can()', () => {
  it('admin y owner pueden gestionar tenant_setup y team', () => {
    for (const role of ['admin', 'owner']) {
      expect(can([role], 'tenant_setup.write', 'RW')).toBe(true);
      expect(can([role], 'team.write', 'RW')).toBe(true);
    }
  });

  it('manager lee team pero no lo edita', () => {
    expect(can(['manager'], 'team.read', 'R')).toBe(true);
    expect(can(['manager'], 'team.write', 'RW')).toBe(false);
  });

  it('viewer/agent no acceden a tenant_setup ni team', () => {
    for (const role of ['viewer', 'agent']) {
      expect(can([role], 'tenant_setup.read', 'R')).toBe(false);
      expect(can([role], 'team.read', 'R')).toBe(false);
    }
  });

  it('platform_owner accede a fleet pero NO al tenant', () => {
    expect(can(['platform_owner'], 'platform.tenants.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'platform.system_health.read', 'R')).toBe(true);
    expect(can(['platform_owner'], 'platform.feature_flags.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'tenant_setup.write', 'RW')).toBe(false);
  });

  it('roles vacíos o desconocidos → false (fail-closed)', () => {
    expect(can([], 'team.read', 'R')).toBe(false);
    expect(can(null, 'team.read', 'R')).toBe(false);
    expect(can(undefined, 'team.read', 'R')).toBe(false);
    expect(can(['unknown_role'], 'team.read', 'R')).toBe(false);
  });

  it('capability desconocida → false', () => {
    expect(can(['owner'], 'nonexistent.capability', 'R')).toBe(false);
  });

  it('multi-rol unifica al rol más permisivo', () => {
    expect(can(['viewer', 'admin'], 'team.write', 'RW')).toBe(true);
  });

  it('R por defecto cuando no se pasa mode', () => {
    expect(can(['manager'], 'team.read')).toBe(true);
    expect(can(['viewer'], 'team.read')).toBe(false);
  });
});

describe('levelFor()', () => {
  it('retorna el nivel exacto declarado', () => {
    expect(levelFor(['manager'], 'team.read')).toBe('R');
    expect(levelFor(['admin'], 'team.write')).toBe('RW');
  });

  it('elige el nivel más alto en multi-rol', () => {
    expect(levelFor(['viewer', 'admin'], 'team.write')).toBe('RW');
  });

  it('null cuando no hay acceso o capability inexistente', () => {
    expect(levelFor(['viewer'], 'team.write')).toBeNull();
    expect(levelFor(['owner'], 'nope.nope')).toBeNull();
    expect(levelFor(null, 'team.read')).toBeNull();
  });
});

describe('highestRole()', () => {
  it('respeta jerarquía platform_owner > owner > admin > manager > agent > viewer', () => {
    expect(highestRole(['viewer', 'admin'])).toBe('admin');
    expect(highestRole(['agent', 'manager'])).toBe('manager');
    expect(highestRole(['owner'])).toBe('owner');
    expect(highestRole(['platform_owner', 'agent'])).toBe('platform_owner');
  });

  it('viewer como fallback seguro', () => {
    expect(highestRole([])).toBe('viewer');
    expect(highestRole(null)).toBe('viewer');
    expect(highestRole(undefined)).toBe('viewer');
    expect(highestRole(['unknown'])).toBe('viewer');
  });
});

describe('resolveActiveRoles()', () => {
  it('toma roles del tenant activo', () => {
    expect(resolveActiveRoles({ tenant: { roles: ['agent'] } })).toEqual(['agent']);
    expect(resolveActiveRoles({ tenant: { role: 'manager' } })).toEqual(['manager']);
  });

  it('platform_owner con support_mode hereda sus roles cross-tenant + owner', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(roles).toContain('viewer');
    expect(roles).toContain('platform_owner');
    expect(roles).toContain('owner');
  });

  it('owner global con support_mode hereda en tenant ajeno', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(roles).toContain('owner');
  });

  it('support_mode SIN owner/platform_owner NO hereda', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['admin'], support_mode: true },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin support_mode los roles del profile no aplican en tenant ajeno', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 't1', roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin tenant ni roles globales → []', () => {
    expect(resolveActiveRoles({})).toEqual([]);
    expect(resolveActiveRoles({ profile: { roles: ['admin'] } })).toEqual([]);
  });

  it('platform_owner SIN tenant aplica aunque support_mode sea false', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['platform_owner']);
  });

  it('supportModeOverride matcheando tenant.id aplica roles globales', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-acme', roles: [] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toContain('platform_owner');
    expect(roles).toContain('owner');
  });

  it('supportModeOverride scoped — no aplica si tenant.id no matchea', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-other', roles: [] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toEqual([]);
  });

  it('comparison de tenant.id usa String() — string vs string', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'abc-123', roles: [] },
      supportModeOverride: { tenantId: 'abc-123', expiresAt: null },
    });
    expect(roles).toContain('platform_owner');
  });

  it('deduplica', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { id: 't1', roles: ['owner', 'admin'] },
    });
    expect(roles.filter((r) => r === 'owner')).toHaveLength(1);
  });
});

describe('ROLE_HOME', () => {
  it('declara landing para todos los roles', () => {
    for (const role of ROLES) {
      expect(ROLE_HOME[role], `landing faltante para ${role}`).toBeTruthy();
    }
  });

  it('platform_owner aterriza en platform-fleet, resto en tenant-setup', () => {
    expect(ROLE_HOME.platform_owner).toBe('platform-fleet');
    for (const role of ['owner', 'admin', 'manager', 'agent', 'viewer']) {
      expect(ROLE_HOME[role]).toBe('tenant-setup');
    }
  });
});
