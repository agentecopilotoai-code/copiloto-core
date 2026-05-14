import { describe, it, expect } from 'vitest';

import {
  ACTOR_TYPE_OPTIONS,
  DPA_POLICY,
  buildFilterPayload,
  emptyFilters,
  formatDate,
} from './auditData.js';

describe('auditData', () => {
  it('emptyFilters starts blank with a default limit of 200', () => {
    expect(emptyFilters()).toEqual({
      action: '',
      actorType: '',
      entityType: '',
      fromDate: '',
      toDate: '',
      limit: '200',
    });
  });

  it('buildFilterPayload drops empty fields and maps to the API shape', () => {
    const payload = buildFilterPayload({
      action: 'quote.created',
      actorType: 'user',
      entityType: '',
      fromDate: '',
      toDate: '2026-05-14T10:00',
      limit: '50',
    });
    expect(payload).toEqual({
      action: 'quote.created',
      actor_type: 'user',
      entity_type: undefined,
      from_date: undefined,
      to_date: '2026-05-14T10:00',
      limit: '50',
    });
  });

  it('buildFilterPayload omits the limit for CSV export', () => {
    const payload = buildFilterPayload(emptyFilters(), { includeLimit: false });
    expect(payload).not.toHaveProperty('limit');
    expect(payload.action).toBeUndefined();
  });

  it('formatDate renders a date or a dash for nullish input', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate('')).toBe('-');
    expect(formatDate('2026-05-14T10:00:00Z')).toMatch(/14\/05/);
  });

  it('ACTOR_TYPE_OPTIONS + DPA_POLICY expose the expected catalogue', () => {
    expect(ACTOR_TYPE_OPTIONS.map((o) => o.value)).toContain('bot');
    expect(ACTOR_TYPE_OPTIONS.map((o) => o.value)).toContain('support');
    expect(DPA_POLICY).toHaveLength(5);
    expect(DPA_POLICY[0].body).toMatch(/no_train/);
  });
});
