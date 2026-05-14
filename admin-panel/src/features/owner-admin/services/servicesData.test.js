import { describe, it, expect } from 'vitest';

import {
  buildPayload,
  buildPreview,
  formatDuration,
  formatPrice,
  formatRecallPreview,
  formFromService,
  normalizeRuleValue,
  rulesFromService,
  rulesToPayload,
} from './servicesData.js';

describe('servicesData', () => {
  it('formatPrice / formatDuration handle empty and valid values', () => {
    expect(formatPrice(null)).toBe('—');
    expect(formatPrice('', 'COP')).toBe('—');
    expect(formatPrice(120000, 'COP')).not.toBe('—');
    expect(formatDuration(0)).toBe('—');
    expect(formatDuration(45)).toBe('45 min');
    expect(formatDuration(90)).toBe('1 h 30 min');
    expect(formatDuration(120)).toBe('2 h');
  });

  it('formatRecallPreview returns null for non-positive intervals', () => {
    expect(formatRecallPreview('')).toBeNull();
    expect(formatRecallPreview(0)).toBeNull();
    expect(formatRecallPreview(-5)).toBeNull();
    expect(formatRecallPreview(180)).not.toBeNull();
  });

  it('normalizeRuleValue coerces by operator', () => {
    // valueless ops drop the value entirely
    expect(normalizeRuleValue('is_null', 'x')).toBeUndefined();
    // list ops split a comma string
    expect(normalizeRuleValue('in', 'a, b ,c')).toEqual(['a', 'b', 'c']);
    // scalar ops coerce booleans / numbers
    expect(normalizeRuleValue('eq', 'true')).toBe(true);
    expect(normalizeRuleValue('eq', '42')).toBe(42);
    expect(normalizeRuleValue('eq', 'hola')).toBe('hola');
  });

  it('rulesToPayload wraps clean rules in all_of and drops invalid ones', () => {
    expect(rulesToPayload([])).toEqual({});
    expect(rulesToPayload([{ key: '', op: 'eq', value: 'x' }])).toEqual({});
    expect(
      rulesToPayload([
        { key: 'budget_tier', op: 'gte', value: '3' },
        { key: 'urgency_level', op: 'is_not_null', value: '' },
      ]),
    ).toEqual({
      all_of: [
        { key: 'budget_tier', op: 'gte', value: 3 },
        { key: 'urgency_level', op: 'is_not_null' },
      ],
    });
  });

  it('rulesFromService round-trips an applies_when payload to form rules', () => {
    const service = {
      applies_when: {
        all_of: [
          { key: 'budget_tier', op: 'gte', value: 3 },
          { key: 'tags', op: 'in', value: ['vip', 'recurrente'] },
        ],
      },
    };
    expect(rulesFromService(service)).toEqual([
      { key: 'budget_tier', op: 'gte', value: '3' },
      { key: 'tags', op: 'in', value: 'vip, recurrente' },
    ]);
    expect(rulesFromService({})).toEqual([]);
  });

  it('buildPayload normalises recall config (empty / zero → null)', () => {
    const base = { name: '  Limpieza  ', duration_minutes: '50', price_amount: '120000' };
    expect(buildPayload({ ...base, recall_interval_days: '' }).recall_interval_days).toBeNull();
    expect(buildPayload({ ...base, recall_interval_days: '0' }).recall_interval_days).toBeNull();
    expect(buildPayload({ ...base, recall_interval_days: '180' }).recall_interval_days).toBe(180);
    const payload = buildPayload({ ...base, recall_interval_days: '90' });
    expect(payload.name).toBe('Limpieza');
    expect(payload.duration_minutes).toBe(50);
    expect(payload.price_amount).toBe(120000);
    expect(payload.applies_when).toEqual({});
  });

  it('buildPreview includes the service name and price', () => {
    const preview = buildPreview(
      { name: 'Botox', price_amount: '380000', price_currency: 'COP', duration_minutes: 30 },
      { label: 'Clínica Norte · acme' },
    );
    expect(preview).toContain('*Botox*');
    expect(preview).toContain('Clínica Norte');
  });

  it('formFromService maps a service record into the edit form shape', () => {
    const form = formFromService({
      name: 'Corte',
      price_amount: 25000,
      recall_interval_days: 90,
      is_active: false,
      applies_when: {},
    });
    expect(form.name).toBe('Corte');
    expect(form.recall_interval_days).toBe('90');
    expect(form.is_active).toBe(false);
    expect(form.applies_when_rules).toEqual([]);
  });
});
