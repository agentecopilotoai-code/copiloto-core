import { describe, it, expect } from 'vitest';

import {
  MAPS_BASE_URL,
  buildMapsUrlFromInputs,
  buildPayload,
  emptyForm,
  formatLocation,
  summarizeHours,
  toForm,
} from './branchesData.js';

describe('branchesData', () => {
  it('emptyForm starts blank with sane defaults', () => {
    const form = emptyForm();
    expect(form.id).toBeNull();
    expect(form.name).toBe('');
    expect(form.country).toBe('CO');
    expect(form.timezone).toBe('America/Bogota');
    expect(form.opening_hours).toEqual({});
    expect(form.is_active).toBe(true);
  });

  it('toForm maps a branch record into the edit-form shape', () => {
    const form = toForm({
      id: 'br-1',
      name: 'Sede Chapinero',
      code: 'chapinero',
      lat: 4.65,
      lng: -74.06,
      opening_hours: { mon: [{ start: '09:00', end: '18:00' }] },
      is_active: false,
    });
    expect(form.id).toBe('br-1');
    expect(form.code).toBe('chapinero');
    expect(form.lat).toBe(4.65);
    expect(form.opening_hours.mon).toHaveLength(1);
    expect(form.is_active).toBe(false);
  });

  it('buildPayload rejects a missing name or code', () => {
    expect(buildPayload({ ...emptyForm(), name: '  ' }).error).toMatch(/nombre/i);
    expect(buildPayload({ ...emptyForm(), name: 'Sede', code: '  ' }).error).toMatch(/código/i);
  });

  it('buildPayload normalises a valid form', () => {
    const { payload, error } = buildPayload({
      ...emptyForm(),
      name: '  Sede Usaquén  ',
      code: '  usaquen  ',
      address: '  Cl. 116 # 7A-15  ',
      country: 'co',
      lat: '4.7',
      lng: '',
      sort_order: '2',
    });
    expect(error).toBeUndefined();
    expect(payload.name).toBe('Sede Usaquén');
    expect(payload.code).toBe('usaquen');
    expect(payload.address).toBe('Cl. 116 # 7A-15');
    expect(payload.country).toBe('CO');
    expect(payload.lat).toBe(4.7);
    expect(payload.lng).toBeNull();
    expect(payload.sort_order).toBe(2);
  });

  it('buildMapsUrlFromInputs prefers valid coordinates over the address', () => {
    const url = buildMapsUrlFromInputs('4.65', '-74.06', 'Cra. 13 # 85-21');
    expect(url).toBe(`${MAPS_BASE_URL}${encodeURIComponent('4.65,-74.06')}`);
  });

  it('buildMapsUrlFromInputs falls back to the address and returns null when empty', () => {
    expect(buildMapsUrlFromInputs('', '', 'Cra. 13 # 85-21')).toBe(
      `${MAPS_BASE_URL}${encodeURIComponent('Cra. 13 # 85-21')}`,
    );
    expect(buildMapsUrlFromInputs('999', '999', 'Cra. 13 # 85-21')).toBe(
      `${MAPS_BASE_URL}${encodeURIComponent('Cra. 13 # 85-21')}`,
    );
    expect(buildMapsUrlFromInputs('', '', '')).toBeNull();
  });

  it('summarizeHours groups adjacent days that share the same ranges', () => {
    const summary = summarizeHours({
      mon: [{ start: '09:00', end: '19:00' }],
      tue: [{ start: '09:00', end: '19:00' }],
      wed: [{ start: '09:00', end: '19:00' }],
      thu: [{ start: '09:00', end: '19:00' }],
      fri: [{ start: '09:00', end: '19:00' }],
      sat: [{ start: '09:00', end: '14:00' }],
    });
    expect(summary).toBe('Lun-Vie 09:00-19:00 · Sáb 09:00-14:00');
    expect(summarizeHours({})).toBe('Sin horario configurado');
  });

  it('formatLocation joins address + city or falls back to a dash', () => {
    expect(formatLocation({ address: 'Cra. 13 # 85-21', city: 'Bogotá' })).toBe(
      'Cra. 13 # 85-21, Bogotá',
    );
    expect(formatLocation({})).toBe('—');
  });
});
