import { describe, it, expect } from 'vitest';

import {
  addRule,
  buildPayload,
  conditionsToRules,
  defaultRule,
  emptySegmentForm,
  fieldKind,
  formFromSegment,
  operatorsForField,
  parseListValue,
  removeRule,
  replaceRule,
  rulesToConditions,
  updateRuleField,
  updateRuleValue,
} from './segmentsData.js';

describe('segmentsData', () => {
  it('resolves the field kind and its operator catalogue', () => {
    expect(fieldKind('total_spent')).toBe('number');
    expect(fieldKind('last_appointment_at')).toBe('date');
    expect(fieldKind('tags')).toBe('array');
    expect(fieldKind('unknown_field')).toBe('text');
    expect(operatorsForField('total_spent')[0].value).toBe('eq');
    expect(operatorsForField('last_appointment_at').map((o) => o.value)).toContain('lt_days_ago');
  });

  it('updates a rule field (resetting the operator) and casts numeric values', () => {
    const updated = updateRuleField(defaultRule(), 'total_spent');
    expect(updated.field).toBe('total_spent');
    expect(updated.op).toBe('eq'); // first operator of the number kind
    expect(updated.value).toBe('');
    // numeric fields cast their value to Number
    expect(updateRuleValue(updated, '500').value).toBe(500);
    // text fields keep the raw string
    expect(updateRuleValue({ field: 'lead_source.channel', op: 'eq' }, 'web').value).toBe('web');
  });

  it('parses comma-separated list values (numbers for between)', () => {
    expect(parseListValue({ field: 'tags', op: 'contains_any' }, 'vip, frecuente, ').value).toEqual([
      'vip',
      'frecuente',
    ]);
    expect(parseListValue({ field: 'total_spent', op: 'between' }, '100, 500').value).toEqual([
      100, 500,
    ]);
  });

  it('adds, replaces and removes rules immutably', () => {
    const items = [defaultRule()];
    const added = addRule(items);
    expect(added).toHaveLength(2);
    expect(items).toHaveLength(1); // original untouched
    const replaced = replaceRule(added, 1, { field: 'tags', op: 'is_empty' });
    expect(replaced[1]).toEqual({ field: 'tags', op: 'is_empty' });
    expect(removeRule(replaced, 0)).toEqual([{ field: 'tags', op: 'is_empty' }]);
  });

  it('round-trips rules ⇄ conditions, dropping empty values', () => {
    const { joiner, items } = rulesToConditions({
      any_of: [{ field: 'tags', op: 'contains_any', value: ['vip'] }],
    });
    expect(joiner).toBe('any_of');
    expect(items).toHaveLength(1);
    // an unknown / non-object rules blob falls back to all_of
    expect(rulesToConditions(null)).toEqual({ joiner: 'all_of', items: [] });
    // conditionsToRules drops rules without a field/op and empty values
    expect(
      conditionsToRules('all_of', [
        { field: 'total_spent', op: 'gt', value: 1000 },
        { field: '', op: 'eq', value: 1 },
        { field: 'last_appointment_at', op: 'is_null', value: '' },
      ]),
    ).toEqual({
      all_of: [
        { field: 'total_spent', op: 'gt', value: 1000 },
        { field: 'last_appointment_at', op: 'is_null' },
      ],
    });
    expect(conditionsToRules('all_of', [])).toEqual({});
  });

  it('builds the payload from a valid form and rejects a missing name', () => {
    const form = {
      ...emptySegmentForm(),
      name: '  Reactivación 60+  ',
      description: '  ',
      kind: 'dynamic',
      joiner: 'all_of',
      items: [{ field: 'last_appointment_at', op: 'lt_days_ago', value: 60 }],
    };
    const { payload, error } = buildPayload(form);
    expect(error).toBeUndefined();
    expect(payload.name).toBe('Reactivación 60+');
    expect(payload.description).toBeNull();
    expect(payload.rules).toEqual({
      all_of: [{ field: 'last_appointment_at', op: 'lt_days_ago', value: 60 }],
    });
    // static segments never carry rules
    expect(buildPayload({ ...form, kind: 'static' }).payload.rules).toEqual({});
    // missing name → error
    expect(buildPayload({ ...emptySegmentForm(), name: '   ' }).error).toMatch(/obligatorio/i);
  });

  it('hydrates the form from a segment record', () => {
    const form = formFromSegment({
      name: 'VIP',
      description: 'Clientes VIP',
      kind: 'dynamic',
      rules: { any_of: [{ field: 'total_spent', op: 'gt', value: 500000 }] },
    });
    expect(form.name).toBe('VIP');
    expect(form.description).toBe('Clientes VIP');
    expect(form.kind).toBe('dynamic');
    expect(form.joiner).toBe('any_of');
    expect(form.items).toEqual([{ field: 'total_spent', op: 'gt', value: 500000 }]);
    // a segment with no rules still yields a default rule row
    expect(formFromSegment({ name: 'Vacío' }).items).toHaveLength(1);
  });
});
