import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import { usePermissions } from './usePermissions.js';

describe('usePermissions()', () => {
  it('viewer en su tenant ve conversaciones pero no toma handoff', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['viewer'] },
        tenant: { roles: ['viewer'] },
      }),
    );
    expect(result.current.roles).toEqual(['viewer']);
    expect(result.current.role).toBe('viewer');
    expect(result.current.can('conversations.view')).toBe(true);
    expect(result.current.can('handoff.take', 'RW')).toBe(false);
  });

  it('agent toma handoff y reintenta DLQ', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['agent'] },
        tenant: { roles: ['agent'] },
      }),
    );
    expect(result.current.can('handoff.take', 'RW')).toBe(true);
    expect(result.current.can('outbound_dlq.retry', 'RW')).toBe(true);
    expect(result.current.can('services.write', 'RW')).toBe(false);
  });

  it('manager edita segmentos y campañas, no servicios', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['manager'] },
        tenant: { roles: ['manager'] },
      }),
    );
    expect(result.current.can('segments.write', 'RW')).toBe(true);
    expect(result.current.can('campaigns.write', 'RW')).toBe(true);
    expect(result.current.can('services.write', 'RW')).toBe(false);
  });

  it('admin gestiona configuración del tenant', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['admin'] },
        tenant: { roles: ['admin'] },
      }),
    );
    expect(result.current.can('services.write', 'RW')).toBe(true);
    expect(result.current.can('team.write', 'RW')).toBe(true);
    expect(result.current.can('legal.write', 'RW')).toBe(true);
    expect(result.current.can('platform.tenants.read')).toBe(false);
  });

  it('platform_owner con support_mode actúa como owner en cualquier tenant', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['platform_owner'], support_mode: true },
        tenant: { roles: ['viewer'] },
      }),
    );
    expect(result.current.isSystemOwner).toBe(true);
    expect(result.current.role).toBe('platform_owner');
    expect(result.current.can('platform.tenants.write', 'RW')).toBe(true);
    // viewer del tenant + platform_owner del profile → viewer accede a conversaciones
    expect(result.current.can('conversations.view')).toBe(true);
  });

  it('platform_owner sin support_mode no escala privilegios', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { roles: ['platform_owner'], support_mode: false },
        tenant: { roles: ['viewer'] },
      }),
    );
    expect(result.current.isSystemOwner).toBe(false);
    expect(result.current.can('platform.tenants.write', 'RW')).toBe(false);
  });

  it('home routea por rol más alto', () => {
    const owner = renderHook(() =>
      usePermissions({ profile: {}, tenant: { roles: ['owner'] } }),
    );
    expect(owner.result.current.home).toBe('dashboard');

    const agent = renderHook(() =>
      usePermissions({ profile: {}, tenant: { roles: ['agent'] } }),
    );
    expect(agent.result.current.home).toBe('operations-desk');

    const platform = renderHook(() =>
      usePermissions({
        profile: { roles: ['platform_owner'], support_mode: true },
        tenant: null,
      }),
    );
    expect(platform.result.current.home).toBe('platform-fleet');
  });

  it('sin tenant ni support_mode el hook devuelve roles vacíos (fail-closed)', () => {
    const { result } = renderHook(() => usePermissions({ profile: {} }));
    expect(result.current.roles).toEqual([]);
    expect(result.current.can('conversations.view')).toBe(false);
    expect(result.current.role).toBe('viewer');
  });

  it('level() expone niveles especiales', () => {
    const agent = renderHook(() =>
      usePermissions({ profile: {}, tenant: { roles: ['agent'] } }),
    );
    expect(agent.result.current.level('contacts.write')).toBe('partial');
    expect(agent.result.current.level('analytics.agent_performance.read')).toBe('own_only');
  });
});
