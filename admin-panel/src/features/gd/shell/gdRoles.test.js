import { describe, it, expect } from 'vitest';

import { gdRoleLabel, gdRolePrimary, gdPrimaryRoleLabel } from './gdRoles.js';

describe('gdRoles', () => {
  it('gdRoleLabel mapea códigos canónicos al label humano', () => {
    expect(gdRoleLabel('gd.admin_sistema')).toBe('Administrador del sistema');
    expect(gdRoleLabel('gd.profesional')).toBe('Profesional responsable');
    expect(gdRoleLabel('gd.usuario_consulta')).toBe('Usuario consulta');
  });

  it('gdRoleLabel formatea roles custom desconocidos', () => {
    expect(gdRoleLabel('gd.mi_rol_custom')).toBe('Mi rol custom');
    expect(gdRoleLabel('cualquier_otro')).toBe('Cualquier otro');
  });

  it('gdRoleLabel maneja null/undefined/empty', () => {
    expect(gdRoleLabel(null)).toBe('Sin rol');
    expect(gdRoleLabel(undefined)).toBe('Sin rol');
    expect(gdRoleLabel('')).toBe('Sin rol');
  });

  it('gdRolePrimary devuelve el rol de mayor jerarquía', () => {
    expect(
      gdRolePrimary(['gd.usuario_consulta', 'gd.admin_sistema']),
    ).toBe('gd.admin_sistema');
    expect(
      gdRolePrimary(['gd.profesional', 'gd.firmante']),
    ).toBe('gd.firmante');
    expect(
      gdRolePrimary(['gd.usuario_dependencia']),
    ).toBe('gd.usuario_dependencia');
  });

  it('gdRolePrimary fallback al primero si no hay match', () => {
    expect(
      gdRolePrimary(['gd.totalmente_custom', 'otro']),
    ).toBe('gd.totalmente_custom');
  });

  it('gdRolePrimary devuelve null para array vacío', () => {
    expect(gdRolePrimary([])).toBeNull();
    expect(gdRolePrimary(null)).toBeNull();
    expect(gdRolePrimary(undefined)).toBeNull();
  });

  it('gdPrimaryRoleLabel combina ambos', () => {
    expect(
      gdPrimaryRoleLabel(['gd.usuario_consulta', 'gd.admin_sistema']),
    ).toBe('Administrador del sistema');
    expect(gdPrimaryRoleLabel([])).toBe('Sin rol');
  });
});
