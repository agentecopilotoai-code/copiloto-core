import { describe, expect, it } from 'vitest';

import { resolveNav } from './resolveNav.js';

const MODULES = [
  { id: 'analytics', label: 'Analítica', capability: 'analytics.tenant.read' },
  { id: 'services', label: 'Servicios', capability: 'services.read' },
  { id: 'team', label: 'Equipo', capability: 'team.write' },
  { id: 'tenant-setup', label: 'Tenant Setup' },
];

const NAV = [
  { section: 'Negocio', items: ['analytics', 'services'] },
  { section: 'Config', items: ['team', 'tenant-setup'] },
  { section: 'Fantasma', items: ['no-existe'] },
];

describe('resolveNav', () => {
  it('omite items sin módulo registrado y secciones vacías', () => {
    const permissions = { can: () => true };
    const groups = resolveNav(NAV, MODULES, permissions);
    expect(groups.map((g) => g.section)).toEqual(['Negocio', 'Config']);
    expect(groups[1].items.map((i) => i.id)).toEqual(['team', 'tenant-setup']);
  });

  it('módulo sin capability siempre es visible', () => {
    const permissions = { can: () => false };
    const groups = resolveNav(NAV, MODULES, permissions);
    expect(groups).toHaveLength(1);
    expect(groups[0].section).toBe('Config');
    expect(groups[0].items.map((i) => i.id)).toEqual(['tenant-setup']);
  });

  it('filtra por permiso con includeDenied=false', () => {
    const permissions = { can: (cap) => cap === 'services.read' };
    const groups = resolveNav(NAV, MODULES, permissions);
    const negocio = groups.find((g) => g.section === 'Negocio');
    expect(negocio.items.map((i) => i.id)).toEqual(['services']);
  });

  it('includeDenied=true conserva items sin permiso como disabled', () => {
    const permissions = { can: (cap) => cap === 'services.read' };
    const groups = resolveNav(NAV, MODULES, permissions, { includeDenied: true });
    const negocio = groups.find((g) => g.section === 'Negocio');
    expect(negocio.items).toEqual([
      { id: 'analytics', label: 'Analítica', capability: 'analytics.tenant.read', disabled: true },
      { id: 'services', label: 'Servicios', capability: 'services.read', disabled: false },
    ]);
  });
});
