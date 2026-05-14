import { describe, it, expect } from 'vitest';

import {
  buildPayload,
  describeServices,
  emptyForm,
  formatPrice,
  toForm,
} from './packagesData.js';

describe('packagesData', () => {
  it('emptyForm starts blank with sane defaults', () => {
    const form = emptyForm();
    expect(form.id).toBeNull();
    expect(form.name).toBe('');
    expect(form.total_sessions).toBe(5);
    expect(form.includes_service_ids).toEqual([]);
    expect(form.is_active).toBe(true);
  });

  it('toForm maps a package record into the edit-form shape', () => {
    const form = toForm({
      id: 'pkg-1',
      name: 'Bono 4 botox',
      total_sessions: 4,
      validity_days: 180,
      price_amount: 1280000,
      includes_service_ids: ['s-1'],
      is_active: false,
    });
    expect(form.id).toBe('pkg-1');
    expect(form.total_sessions).toBe(4);
    expect(form.validity_days).toBe(180);
    expect(form.includes_service_ids).toEqual(['s-1']);
    expect(form.is_active).toBe(false);
  });

  it('buildPayload rejects an empty name or a non-positive session count', () => {
    expect(buildPayload({ ...emptyForm(), name: '   ' }).error).toMatch(/nombre/i);
    expect(buildPayload({ ...emptyForm(), name: 'X', total_sessions: 0 }).error).toMatch(
      /sesiones/i,
    );
  });

  it('buildPayload normalises a valid form', () => {
    const { payload, error } = buildPayload({
      id: 'pkg-1',
      name: '  Plan trimestral  ',
      description: '  ',
      total_sessions: '6',
      validity_days: '',
      price_amount: '680000',
      price_currency: 'cop',
      includes_service_ids: ['s-1', 's-2'],
      is_active: true,
      sort_order: '2',
    });
    expect(error).toBeUndefined();
    expect(payload).toEqual({
      name: 'Plan trimestral',
      description: null,
      total_sessions: 6,
      validity_days: null,
      price_amount: 680000,
      price_currency: 'COP',
      includes_service_ids: ['s-1', 's-2'],
      is_active: true,
      sort_order: 2,
    });
  });

  it('describeServices labels the included services or falls back to "any"', () => {
    const map = new Map([
      ['s-1', { id: 's-1', name: 'Limpieza facial' }],
      ['s-2', { id: 's-2', name: 'Botox' }],
    ]);
    expect(describeServices([], map)).toBe('Aplica a cualquier servicio');
    expect(describeServices(['s-1', 's-2'], map)).toBe('Limpieza facial, Botox');
  });

  it('formatPrice handles nullish and valid amounts', () => {
    expect(formatPrice(null)).toBe('—');
    expect(formatPrice('', 'COP')).toBe('—');
    expect(formatPrice(420000, 'COP')).not.toBe('—');
  });
});
