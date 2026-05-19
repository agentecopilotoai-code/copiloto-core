/**
 * Cover the branches in useTenantOptions (currently 46.66% branches).
 */
import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTenantOptions } from './useTenantOptions.js';


describe('useTenantOptions', () => {
  it('returns empty array when no profile', () => {
    const { result } = renderHook(() => useTenantOptions(undefined));
    expect(result.current).toEqual([]);
  });

  it('returns empty array when profile has no tenant_id', () => {
    const { result } = renderHook(() => useTenantOptions({ name: 'X' }));
    expect(result.current).toEqual([]);
  });

  it('returns single tenant option when profile is fully populated', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-1',
        tenant_slug: 'acme',
        tenant_name: 'Acme Inc.',
        roles: ['admin', 'owner'],
      }),
    );
    expect(result.current).toHaveLength(1);
    expect(result.current[0]).toMatchObject({
      id: 'tid-1',
      slug: 'acme',
      display_name: 'Acme Inc.',
      is_default: true,
    });
    // role should be picked from roles array (owner > admin)
    expect(result.current[0].roles).toEqual(['admin', 'owner']);
  });

  it('falls back to slug=tenant when slug is missing', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-2',
        roles: ['agent'],
      }),
    );
    expect(result.current[0].slug).toBe('tenant');
    expect(result.current[0].display_name).toBe('tenant');
  });

  it('handles non-array roles defensively', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-3',
        tenant_slug: 'x',
        roles: 'not-an-array',
      }),
    );
    expect(result.current[0].roles).toEqual([]);
  });

  it('uses tenant_name when present, otherwise slug', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-4',
        tenant_slug: 'mybiz',
        tenant_name: 'My Business',
        roles: ['viewer'],
      }),
    );
    expect(result.current[0].display_name).toBe('My Business');
  });

  it('label includes slug and role', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-5',
        tenant_slug: 'lab',
        roles: ['admin'],
      }),
    );
    expect(result.current[0].label).toContain('lab');
    expect(result.current[0].label).toContain('admin');
  });

  it('defaults role to viewer when roles is empty', () => {
    const { result } = renderHook(() =>
      useTenantOptions({
        tenant_id: 'tid-6',
        tenant_slug: 'noroles',
        roles: [],
      }),
    );
    // label should fall back to "viewer"
    expect(result.current[0].label).toContain('viewer');
  });
});
