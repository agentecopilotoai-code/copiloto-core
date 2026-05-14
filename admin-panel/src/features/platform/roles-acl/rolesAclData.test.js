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
    expect(categorizeCapability('conversations.view')).toBe('Operación diaria');
    expect(categorizeCapability('campaigns.write')).toBe('Análisis y crecimiento');
    expect(categorizeCapability('services.read')).toBe('Configuración del negocio');
    expect(categorizeCapability('whatsapp.read')).toBe('Canales e IA');
    expect(categorizeCapability('team.write')).toBe('Administración del tenant');
    expect(categorizeCapability('platform.tenants.read')).toBe('Platform Owner · fleet');
    expect(categorizeCapability('mystery.capability')).toBe('Otros');
  });

  it('builds every capability into an ordered, grouped matrix', () => {
    const groups = buildMatrixGroups();
    // Groups come back in GROUP_ORDER.
    const seen = groups.map((g) => g.group);
    expect(seen).toEqual(GROUP_ORDER.filter((g) => seen.includes(g)));
    // Every capability in PERMISSIONS is represented exactly once.
    const flat = groups.flatMap((g) => g.rows.map((r) => r.capability));
    expect(flat.sort()).toEqual(Object.keys(PERMISSIONS).sort());
  });

  it('filters the matrix by a case-insensitive capability search', () => {
    const groups = buildMatrixGroups('PLATFORM');
    const flat = groups.flatMap((g) => g.rows.map((r) => r.capability));
    expect(flat.length).toBeGreaterThan(0);
    expect(flat.every((cap) => cap.startsWith('platform.'))).toBe(true);
    // A search matching nothing yields no groups.
    expect(buildMatrixGroups('zzz-no-match')).toEqual([]);
  });

  it('counts capabilities each role has any access to', () => {
    const counts = countCapabilitiesPerRole();
    for (const role of ROLES) {
      expect(typeof counts[role]).toBe('number');
    }
    // platform_owner only has the platform.* capabilities; viewer has fewer
    // than admin (admin is a superset of read-ish + write capabilities).
    expect(counts.platform_owner).toBeGreaterThan(0);
    expect(counts.admin).toBeGreaterThan(counts.viewer);
  });
});
