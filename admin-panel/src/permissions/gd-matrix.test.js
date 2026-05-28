import { describe, it, expect } from 'vitest';
import {
  GD_ROLES,
  GD_PERMISSIONS,
  GD_LANDING_BY_ROLE,
  gdCan,
  gdCanAny,
  gdLandingFor,
  hasAnyGdAccess,
} from './gd-matrix.js';

describe('gd-matrix', () => {
  it('expone los 17 roles GD con UI (los 2 técnicos quedan fuera)', () => {
    expect(GD_ROLES).toHaveLength(17);
    expect(GD_ROLES).toContain('gd.admin_sistema');
    expect(GD_ROLES).toContain('gd.radicador');
    expect(GD_ROLES).not.toContain('gd.agente_ia');
    expect(GD_ROLES).not.toContain('gd.robot_rpa');
  });

  it('PERMISSIONS contiene los códigos críticos esperados', () => {
    expect(GD_PERMISSIONS['VU-001']).toBeDefined();
    expect(GD_PERMISSIONS['PQRSD-009']).toBeDefined();
    expect(GD_PERMISSIONS['TRD-001']).toBeDefined();
    expect(GD_PERMISSIONS['PER-001']).toBeDefined();
    // IA embebida (UI-12 / EP-010).
    expect(GD_PERMISSIONS['IA-001']).toBeDefined();
    expect(GD_PERMISSIONS['IA-008']).toBeDefined();
    // Correo + alertas (UI-13 / EP-011/012).
    expect(GD_PERMISSIONS['COR-EMAIL-001']).toBeDefined();
    expect(GD_PERMISSIONS['COR-EMAIL-006']).toBeDefined();
    expect(GD_PERMISSIONS['ALR-001']).toBeDefined();
    expect(GD_PERMISSIONS['ALR-002']).toBeDefined();
  });

  describe('Correo + alertas (UI-13)', () => {
    it('radicador puede ver y radicar correo entrante', () => {
      expect(gdCan('gd.radicador', 'COR-EMAIL-001', 'RW')).toBe(true);
      expect(gdCan('gd.radicador', 'COR-EMAIL-002', 'RW')).toBe(true);
    });
    it('profesional puede ver correo entrante (R) pero no radicarlo', () => {
      expect(gdCan('gd.profesional', 'COR-EMAIL-001', 'R')).toBe(true);
      expect(gdCan('gd.profesional', 'COR-EMAIL-002', 'RW')).toBe(false);
    });
    it('admin sistema RW en config canales y reglas auto-clasif', () => {
      expect(gdCan('gd.admin_sistema', 'COR-EMAIL-004', 'RW')).toBe(true);
      expect(gdCan('gd.admin_sistema', 'COR-EMAIL-005', 'RW')).toBe(true);
    });
    it('usuario consulta no accede a config canales', () => {
      expect(gdCan('gd.usuario_consulta', 'COR-EMAIL-004')).toBe(false);
    });
    it('jefe dependencia puede atender alertas', () => {
      expect(gdCan('gd.jefe_dependencia', 'ALR-002', 'RW')).toBe(true);
    });
    it('auditor solo lee alertas', () => {
      expect(gdCan('gd.auditor', 'ALR-001', 'R')).toBe(true);
      expect(gdCan('gd.auditor', 'ALR-002', 'RW')).toBe(false);
    });
    it('todos los roles GD leen y configuran notificaciones (existentes NOT-*)', () => {
      expect(gdCan('gd.profesional', 'NOT-READ', 'R')).toBe(true);
      expect(gdCan('gd.profesional', 'NOT-PREF', 'RW')).toBe(true);
    });
  });

  describe('IA permisos (UI-12)', () => {
    it('profesional puede invocar sugerencia clasificación', () => {
      expect(gdCan('gd.profesional', 'IA-001', 'RW')).toBe(true);
    });
    it('admin sistema RW en config modelos IA', () => {
      expect(gdCan('gd.admin_sistema', 'IA-008', 'RW')).toBe(true);
    });
    it('usuario_consulta NO puede actualizar config modelos', () => {
      expect(gdCan('gd.usuario_consulta', 'IA-008', 'RW')).toBe(false);
    });
    it('auditor lee panel uso IA', () => {
      expect(gdCan('gd.auditor', 'IA-006', 'R')).toBe(true);
      expect(gdCan('gd.auditor', 'IA-006', 'RW')).toBe(false);
    });
    it('admin_seguridad RW en detección PII', () => {
      expect(gdCan('gd.admin_seguridad', 'IA-005', 'RW')).toBe(true);
    });
  });

  describe('gdCan', () => {
    it('radicador puede crear radicado de entrada (VU-001 RW)', () => {
      expect(gdCan('gd.radicador', 'VU-001', 'R')).toBe(true);
      expect(gdCan('gd.radicador', 'VU-001', 'RW')).toBe(true);
    });

    it('profesional NO puede crear radicado de entrada', () => {
      expect(gdCan('gd.profesional', 'VU-001')).toBe(false);
    });

    it('jefe_dependencia puede aprobar respuesta PQRSD (RW)', () => {
      expect(gdCan('gd.jefe_dependencia', 'PQRSD-015', 'RW')).toBe(true);
    });

    it('auditor puede consultar auditoría (R) pero no escribir USR-001', () => {
      expect(gdCan('gd.auditor', 'AUD-001', 'R')).toBe(true);
      expect(gdCan('gd.auditor', 'USR-001')).toBe(false);
    });

    it('roles desconocidos / permisos inexistentes → false', () => {
      expect(gdCan('foo', 'VU-001')).toBe(false);
      expect(gdCan('gd.radicador', 'NO-EXISTE')).toBe(false);
      expect(gdCan(null, 'VU-001')).toBe(false);
      expect(gdCan('gd.radicador', null)).toBe(false);
    });

    it('R no implica RW pero RW implica R', () => {
      expect(gdCan('gd.auditor', 'AUD-001', 'R')).toBe(true);
      expect(gdCan('gd.auditor', 'AUD-001', 'RW')).toBe(false);
    });
  });

  describe('gdCanAny', () => {
    it('OR sobre múltiples roles', () => {
      expect(
        gdCanAny(['gd.profesional', 'gd.radicador'], 'VU-001'),
      ).toBe(true);
      expect(gdCanAny(['gd.profesional'], 'VU-001')).toBe(false);
    });
    it('lista vacía o no array → false', () => {
      expect(gdCanAny([], 'VU-001')).toBe(false);
      expect(gdCanAny(null, 'VU-001')).toBe(false);
    });
  });

  describe('gdLandingFor', () => {
    it('mapea cada rol a su landing', () => {
      expect(gdLandingFor('gd.radicador')).toBe('/gd/ventanilla');
      expect(gdLandingFor('gd.jefe_dependencia')).toBe('/gd/buzon/dependencia');
      expect(gdLandingFor('gd.auditor')).toBe('/gd/auditoria');
    });
    it('toma el PRIMER rol con landing en el array', () => {
      expect(gdLandingFor(['gd.usuario_consulta', 'gd.radicador'])).toBe('/gd/consulta');
    });
    it('rol desconocido → /gd', () => {
      expect(gdLandingFor('foo')).toBe('/gd');
      expect(gdLandingFor([])).toBe('/gd');
      expect(gdLandingFor(null)).toBe('/gd');
    });
  });

  describe('hasAnyGdAccess', () => {
    it('true si tiene al menos un rol gd', () => {
      expect(hasAnyGdAccess(['gd.profesional'])).toBe(true);
      expect(hasAnyGdAccess(['admin', 'gd.auditor'])).toBe(true);
    });
    it('false si no tiene ningún rol gd', () => {
      expect(hasAnyGdAccess(['admin'])).toBe(false);
      expect(hasAnyGdAccess([])).toBe(false);
      expect(hasAnyGdAccess(null)).toBe(false);
    });
  });

  it('GD_LANDING_BY_ROLE cubre todos los roles GD del catálogo', () => {
    for (const role of GD_ROLES) {
      expect(GD_LANDING_BY_ROLE[role]).toMatch(/^\/gd/);
    }
  });
});
