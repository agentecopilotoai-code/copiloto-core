import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import { usePermissions } from '../permissions/index.js';
import { shellForRole } from './AdminLayout.jsx';
import { PlatformOwnerShell } from './shells/PlatformOwnerShell.jsx';
import { ReadOnlyShell } from './shells/ReadOnlyShell.jsx';
import { TenantShell } from './shells/TenantShell.jsx';

describe('shellForRole', () => {
  it('viewer → ReadOnlyShell', () => {
    const { result } = renderHook(() =>
      usePermissions({ profile: {}, tenant: { roles: ['viewer'] } }),
    );
    expect(result.current.role).toBe('viewer');
    expect(shellForRole(result.current.role)).toBe(ReadOnlyShell);
  });

  it('platform_owner en support_mode → PlatformOwnerShell', () => {
    const { result } = renderHook(() =>
      usePermissions({
        profile: { support_mode: true, roles: ['platform_owner'] },
        tenant: null,
      }),
    );
    expect(result.current.role).toBe('platform_owner');
    expect(shellForRole(result.current.role)).toBe(PlatformOwnerShell);
  });

  it.each(['owner', 'admin', 'manager', 'agent'])(
    '%s → TenantShell',
    (role) => {
      const { result } = renderHook(() =>
        usePermissions({ profile: {}, tenant: { roles: [role] } }),
      );
      expect(result.current.role).toBe(role);
      expect(shellForRole(result.current.role)).toBe(TenantShell);
    },
  );
});
