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

  it('usa solo niveles válidos', () => {
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

  it('platform_owner NO ve capabilities de tenant', () => {
    const TENANT_ONLY = [
      'conversations.view', 'handoff.take', 'appointments.view',
      'services.write', 'campaigns.write', 'segments.write',
      'team.write', 'legal.write', 'audit.read',
    ];
    for (const cap of TENANT_ONLY) {
      expect(PERMISSIONS[cap].platform_owner, `${cap} no debe ser visible a platform_owner`).toBeNull();
    }
  });
});

describe('can()', () => {
  it('viewer puede leer conversaciones pero no tomarlas', () => {
    expect(can(['viewer'], 'conversations.view', 'R')).toBe(true);
    expect(can(['viewer'], 'conversations.view', 'RW')).toBe(false);
    expect(can(['viewer'], 'handoff.take', 'R')).toBe(false);
    expect(can(['viewer'], 'handoff.take', 'RW')).toBe(false);
  });

  it('agent puede tomar handoff y editar contactos parcialmente', () => {
    expect(can(['agent'], 'handoff.take', 'RW')).toBe(true);
    expect(can(['agent'], 'contacts.write', 'R')).toBe(true);
    expect(can(['agent'], 'contacts.write', 'RW')).toBe(false); // partial, no RW
  });

  it('manager gestiona segmentos y campañas pero no servicios', () => {
    expect(can(['manager'], 'segments.write', 'RW')).toBe(true);
    expect(can(['manager'], 'campaigns.write', 'RW')).toBe(true);
    expect(can(['manager'], 'services.write', 'RW')).toBe(false);
    expect(can(['manager'], 'services.write', 'R')).toBe(false);
  });

  it('admin gestiona servicios, paquetes, equipo y legal', () => {
    expect(can(['admin'], 'services.write', 'RW')).toBe(true);
    expect(can(['admin'], 'packages.write', 'RW')).toBe(true);
    expect(can(['admin'], 'team.write', 'RW')).toBe(true);
    expect(can(['admin'], 'legal.write', 'RW')).toBe(true);
    expect(can(['admin'], 'audit.read', 'R')).toBe(true);
  });

  it('owner tiene los mismos privilegios que admin sobre el tenant', () => {
    expect(can(['owner'], 'services.write', 'RW')).toBe(true);
    expect(can(['owner'], 'team.write', 'RW')).toBe(true);
    expect(can(['owner'], 'tenant_setup.write', 'RW')).toBe(true);
  });

  it('go_live_readiness.mark_live es exclusivo del owner del tenant', () => {
    // UI-016.1: marcar el tenant como live es una operación de cierre que solo
    // el owner del negocio debe poder ejecutar. Admin lee el checklist pero no
    // dispara el go-live.
    expect(can(['owner'], 'go_live_readiness.mark_live', 'RW')).toBe(true);
    expect(can(['owner'], 'go_live_readiness.read', 'R')).toBe(true);
    expect(can(['admin'], 'go_live_readiness.read', 'R')).toBe(true);
    expect(can(['admin'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
    expect(can(['manager'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
    expect(can(['platform_owner'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
  });

  it('platform_owner accede a la flota pero NO al tenant', () => {
    expect(can(['platform_owner'], 'platform.tenants.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'platform.system_health.read', 'R')).toBe(true);
    expect(can(['platform_owner'], 'platform.feature_flags.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'campaigns.write', 'R')).toBe(false);
    expect(can(['platform_owner'], 'conversations.view', 'R')).toBe(false);
  });

  it('roles vacíos o desconocidos → false (fail-closed)', () => {
    expect(can([], 'conversations.view', 'R')).toBe(false);
    expect(can(null, 'conversations.view', 'R')).toBe(false);
    expect(can(undefined, 'conversations.view', 'R')).toBe(false);
    expect(can(['unknown_role'], 'conversations.view', 'R')).toBe(false);
  });

  it('capability desconocida → false', () => {
    expect(can(['owner'], 'nonexistent.capability', 'R')).toBe(false);
  });

  it('multi-rol unifica al rol más permisivo', () => {
    // Un usuario que tiene viewer + manager → debe poder gestionar segmentos.
    expect(can(['viewer', 'manager'], 'segments.write', 'RW')).toBe(true);
    // viewer + agent → contactos.write partial ok en R, no RW.
    expect(can(['viewer', 'agent'], 'contacts.write', 'R')).toBe(true);
    expect(can(['viewer', 'agent'], 'contacts.write', 'RW')).toBe(false);
  });

  it('R por defecto cuando no se pasa mode', () => {
    expect(can(['agent'], 'contacts.write')).toBe(true);
    expect(can(['viewer'], 'segments.write')).toBe(false);
  });
});

describe('levelFor()', () => {
  it('retorna el nivel exacto declarado', () => {
    expect(levelFor(['viewer'], 'conversations.view')).toBe('R');
    expect(levelFor(['agent'], 'handoff.take')).toBe('RW');
    expect(levelFor(['agent'], 'contacts.write')).toBe('partial');
    expect(levelFor(['agent'], 'analytics.agent_performance.read')).toBe('own_only');
    expect(levelFor(['admin'], 'services.write')).toBe('RW');
  });

  it('elige el nivel más alto en multi-rol', () => {
    expect(levelFor(['viewer', 'admin'], 'services.write')).toBe('RW');
    expect(levelFor(['agent', 'manager'], 'contacts.write')).toBe('RW');
  });

  it('null cuando no hay acceso o capability inexistente', () => {
    expect(levelFor(['viewer'], 'campaigns.write')).toBeNull();
    expect(levelFor(['owner'], 'nope.nope')).toBeNull();
    expect(levelFor(null, 'conversations.view')).toBeNull();
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

  it('platform_owner con support_mode hereda sus roles cross-tenant', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toContain('viewer');
    expect(roles).toContain('platform_owner');
  });

  it('owner con support_mode hereda sus roles', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toContain('owner');
  });

  it('support_mode SIN owner/platform_owner NO hereda', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['admin'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin support_mode los roles del profile no aplican', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin tenant ni roles globales → [] (fail-closed)', () => {
    expect(resolveActiveRoles({})).toEqual([]);
    // `admin` no es rol global; sin tenant activo no aplica.
    expect(resolveActiveRoles({ profile: { roles: ['admin'] } })).toEqual([]);
    expect(resolveActiveRoles({ profile: { roles: ['agent', 'manager'] } })).toEqual([]);
  });

  it('BUG-006: platform_owner SIN tenant aplica aunque support_mode sea false', () => {
    // Contexto: vistas globales de plataforma (`/platform`, IndexRedirect).
    // El platform_owner debe ser reconocido SIEMPRE — sin esto, el redirect
    // post-login lo manda al onboarding de tenant en vez de /platform.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['platform_owner']);
  });

  it('BUG-006: owner SIN tenant aplica aunque support_mode sea false', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['owner']);
  });

  it('BUG-006: sin tenant solo aplican roles globales — admin/agent del profile no se filtran', () => {
    // Si el profile trae [platform_owner, admin], solo platform_owner cuenta
    // a nivel global (admin no es rol global). El admin solo aplica dentro de
    // un tenant activo.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner', 'admin'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['platform_owner']);
  });

  it('TASK-0077 preservado: platform_owner CON tenant requiere support_mode para heredar', () => {
    // El fix de BUG-006 NO debe romper TASK-0077: operar EN un tenant ajeno
    // con privilegios elevados sigue requiriendo support_mode explícito.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
    expect(roles).not.toContain('platform_owner');
  });

  it('deduplica', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { roles: ['owner', 'admin'] },
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

  it('agent aterriza en operations-desk, platform_owner en fleet', () => {
    expect(ROLE_HOME.agent).toBe('operations-desk');
    expect(ROLE_HOME.platform_owner).toBe('platform-fleet');
  });

  it('viewer aterriza en viewer-summary (UI-010.1)', () => {
    expect(ROLE_HOME.viewer).toBe('viewer-summary');
  });
});
