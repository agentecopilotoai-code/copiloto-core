import { describe, expect, it } from 'vitest';

import { computePermissions } from './usePermissions.js';

// Estos tests cubren la lógica pura de resolución de permisos (matriz +
// merge de roles + safe-home). Antes corrían contra `usePermissions` con
// args `{profile, tenant}`. Después de BUG-220 ese hook solo lee del
// context (single source) — los tests pasaron a `computePermissions`,
// que es la misma lógica como función pura. El hook se sigue cubriendo
// con tests de integración (router.test.jsx, ContactProfile.test.jsx,
// etc.) que ejercen el context-binding real.
describe('computePermissions()', () => {
  it('viewer en su tenant ve conversaciones pero no toma handoff', () => {
    const p = computePermissions({
      profile: { roles: ['viewer'] },
      tenant: { roles: ['viewer'] },
    });
    expect(p.roles).toEqual(['viewer']);
    expect(p.role).toBe('viewer');
    expect(p.can('conversations.view')).toBe(true);
    expect(p.can('handoff.take', 'RW')).toBe(false);
  });

  it('agent toma handoff y reintenta DLQ', () => {
    const p = computePermissions({
      profile: { roles: ['agent'] },
      tenant: { roles: ['agent'] },
    });
    expect(p.can('handoff.take', 'RW')).toBe(true);
    expect(p.can('outbound_dlq.retry', 'RW')).toBe(true);
    expect(p.can('services.write', 'RW')).toBe(false);
  });

  it('manager edita segmentos y campañas, no servicios', () => {
    const p = computePermissions({
      profile: { roles: ['manager'] },
      tenant: { roles: ['manager'] },
    });
    expect(p.can('segments.write', 'RW')).toBe(true);
    expect(p.can('campaigns.write', 'RW')).toBe(true);
    expect(p.can('services.write', 'RW')).toBe(false);
  });

  it('admin gestiona configuración del tenant', () => {
    const p = computePermissions({
      profile: { roles: ['admin'] },
      tenant: { roles: ['admin'] },
    });
    expect(p.can('services.write', 'RW')).toBe(true);
    expect(p.can('team.write', 'RW')).toBe(true);
    expect(p.can('legal.write', 'RW')).toBe(true);
    expect(p.can('platform.tenants.read')).toBe(false);
  });

  it('platform_owner con support_mode actúa como owner en cualquier tenant', () => {
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(p.isSystemOwner).toBe(true);
    expect(p.role).toBe('platform_owner');
    expect(p.can('platform.tenants.write', 'RW')).toBe(true);
    // viewer del tenant + platform_owner del profile → viewer accede a conversaciones
    expect(p.can('conversations.view')).toBe(true);
  });

  it('platform_owner sin support_mode no escala privilegios', () => {
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { roles: ['viewer'] },
    });
    expect(p.isSystemOwner).toBe(false);
    expect(p.can('platform.tenants.write', 'RW')).toBe(false);
  });

  it('home routea por rol más alto', () => {
    const owner = computePermissions({ profile: {}, tenant: { roles: ['owner'] } });
    expect(owner.home).toBe('dashboard');

    const agent = computePermissions({ profile: {}, tenant: { roles: ['agent'] } });
    expect(agent.home).toBe('operations-desk');

    const platform = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: null,
    });
    expect(platform.home).toBe('platform-fleet');
  });

  it('sin tenant ni roles globales el hook devuelve vacío (fail-closed)', () => {
    const p = computePermissions({ profile: {} });
    expect(p.roles).toEqual([]);
    expect(p.can('conversations.view')).toBe(false);
    expect(p.role).toBe('viewer');
  });

  it('BUG-006: platform_owner SIN support_mode resuelve home /platform sin tenant', () => {
    // Reproduce el escenario que mandaba al onboarding: usuario con rol
    // global platform_owner, support_mode false (default), sin tenant en
    // contexto. Debe reconocerlo como platform_owner y resolver el home a
    // `platform-fleet` para que IndexRedirect redirija a /platform.
    const p = computePermissions({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: null,
    });
    expect(p.role).toBe('platform_owner');
    expect(p.home).toBe('platform-fleet');
    expect(p.can('platform.tenants.write', 'RW')).toBe(true);
    // isSystemOwner sigue ligado a support_mode (es el banner cross-tenant).
    expect(p.isSystemOwner).toBe(false);
  });

  it('level() expone niveles especiales', () => {
    const agent = computePermissions({ profile: {}, tenant: { roles: ['agent'] } });
    expect(agent.level('contacts.write')).toBe('partial');
    expect(agent.level('analytics.agent_performance.read')).toBe('own_only');
  });
});
