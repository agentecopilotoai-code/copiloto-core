import { describe, it, expect } from 'vitest';

import {
  buildMatrixGroups,
  categorizeCapability,
  countCapabilitiesPerRole,
  GROUP_ORDER,
} from './rolesAclData.js';
import { PERMISSIONS, ROLES } from '../../../permissions/index.js';

describe('rolesAclData', () => {
  it('categorizes capability keys by domain', () => {
    expect(categorizeCapability('tenant_setup.write')).toBe('Administración del tenant');
    expect(categorizeCapability('team.write')).toBe('Administración del tenant');
    expect(categorizeCapability('platform.tenants.read')).toBe('Platform Owner · fleet');
    expect(categorizeCapability('mystery.capability')).toBe('Otros');
  });

  it('builds every capability into an ordered, grouped matrix', () => {
    const groups = buildMatrixGroups();
    const seen = groups.map((g) => g.group);
    expect(seen).toEqual(GROUP_ORDER.filter((g) => seen.includes(g)));
    const flat = groups.flatMap((g) => g.rows.map((r) => r.capability));
    expect(flat.sort()).toEqual(Object.keys(PERMISSIONS).sort());
  });

  it('filters the matrix by a case-insensitive capability search', () => {
    const groups = buildMatrixGroups('PLATFORM');
    const flat = groups.flatMap((g) => g.rows.map((r) => r.capability));
    expect(flat.length).toBeGreaterThan(0);
    expect(flat.every((cap) => cap.startsWith('platform.'))).toBe(true);
    expect(buildMatrixGroups('zzz-no-match')).toEqual([]);
  });

  it('counts capabilities each role has any access to', () => {
    const counts = countCapabilitiesPerRole();
    for (const role of ROLES) {
      expect(typeof counts[role]).toBe('number');
    }
    expect(counts.platform_owner).toBeGreaterThan(0);
    expect(counts.admin).toBeGreaterThan(counts.viewer);
  });
});
