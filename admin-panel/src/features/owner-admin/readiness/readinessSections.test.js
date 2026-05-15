import { describe, it, expect } from 'vitest';

import {
  buildChecklistCsv,
  formatCheckDetails,
  groupChecksBySection,
  SECTION_ORDER,
} from './readinessSections.js';

describe('groupChecksBySection', () => {
  it('agrupa por sección y respeta el orden declarativo', () => {
    const checks = [
      { key: 'whatsapp_channel', ready: true, label: 'WA channel' },
      { key: 'tenant_active', ready: true, label: 'Tenant live' },
      { key: 'audit', ready: false, label: 'Audit eventos' },
    ];
    const grouped = groupChecksBySection(checks);
    expect(grouped.map((g) => g.section.id)).toEqual(['tenant', 'whatsapp', 'operations']);
    expect(grouped[0].checks).toHaveLength(1);
    expect(grouped[2].passed).toBe(0);
    expect(grouped[2].total).toBe(1);
  });

  it('cae a la sección "general" cuando llega una key desconocida (fail-soft)', () => {
    const grouped = groupChecksBySection([
      { key: 'unknown_new_check', ready: false, label: 'Nuevo' },
    ]);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].section.id).toBe('general');
    expect(grouped[0].passed).toBe(0);
  });

  it('omite secciones sin checks', () => {
    const grouped = groupChecksBySection([
      { key: 'tenant_active', ready: true, label: 'X' },
    ]);
    expect(grouped.map((g) => g.section.id)).toEqual(['tenant']);
  });

  it('acepta un array vacío o nulo sin reventar', () => {
    expect(groupChecksBySection([])).toEqual([]);
    expect(groupChecksBySection(null)).toEqual([]);
    expect(groupChecksBySection(undefined)).toEqual([]);
  });

  it('SECTION_ORDER contiene los 6 buckets esperados', () => {
    expect(SECTION_ORDER).toEqual([
      'tenant',
      'whatsapp',
      'retrieval',
      'operations',
      'billing',
      'general',
    ]);
  });
});

describe('formatCheckDetails', () => {
  it('devuelve string vacío para entradas vacías', () => {
    expect(formatCheckDetails()).toBe('');
    expect(formatCheckDetails(null)).toBe('');
    expect(formatCheckDetails({})).toBe('');
  });

  it('formatea pares clave:valor separados por punto medio, máximo 4', () => {
    const out = formatCheckDetails({ a: 1, b: 2, c: 3, d: 4, e: 5 });
    expect(out).toBe('a: 1 · b: 2 · c: 3 · d: 4');
  });

  it('omite valores null/undefined/string vacío', () => {
    expect(formatCheckDetails({ a: 1, b: null, c: '', d: undefined, e: 'ok' })).toBe('a: 1 · e: ok');
  });

  it('serializa objetos anidados con JSON', () => {
    expect(formatCheckDetails({ meta: { x: 1 } })).toBe('meta: {"x":1}');
  });
});

describe('buildChecklistCsv', () => {
  it('emite header + filas con tenant_id/checked_at/ready en comentarios', () => {
    const grouped = groupChecksBySection([
      { key: 'tenant_active', ready: true, label: 'Tenant live', reason: 'status = live' },
      { key: 'handoff', ready: false, label: 'Handoff', reason: 'sin test E2E' },
    ]);
    const csv = buildChecklistCsv(grouped, {
      tenant_id: 't-1',
      checked_at: '2026-05-15T12:00:00Z',
      ready: false,
    });
    expect(csv).toContain('seccion,check,estado,detalle');
    expect(csv).toContain('# tenant_id=t-1');
    expect(csv).toContain('# checked_at=2026-05-15T12:00:00Z');
    expect(csv).toContain('# ready=false');
    expect(csv).toContain('"Tenant activo y configurado","Tenant live",OK,"status = live"');
    expect(csv).toContain('"Operación y handoff","Handoff",PENDIENTE,"sin test E2E"');
  });

  it('escapa comillas en label/reason siguiendo la convención CSV', () => {
    const grouped = groupChecksBySection([
      { key: 'tenant_active', ready: true, label: 'Tenant "live"', reason: '"plan Pro"' },
    ]);
    const csv = buildChecklistCsv(grouped, { tenant_id: 't', checked_at: '', ready: true });
    expect(csv).toContain('"Tenant ""live""",OK,"""plan Pro"""');
  });
});
