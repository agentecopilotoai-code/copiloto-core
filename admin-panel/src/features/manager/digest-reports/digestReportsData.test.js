import { describe, it, expect } from 'vitest';

import {
  CADENCE_OPTIONS,
  cadenceLabel,
  emptyForm,
  formatLastSent,
  recipientInitials,
  recipientLabel,
  summarizeSubscriptions,
} from './digestReportsData.js';

describe('digestReportsData', () => {
  it('CADENCE_OPTIONS exposes daily and weekly; emptyForm starts blank', () => {
    expect(CADENCE_OPTIONS.map((o) => o.value)).toEqual(['daily', 'weekly']);
    expect(emptyForm()).toEqual({
      recipient_email: '',
      recipient_whatsapp: '',
      cadence: 'daily',
      enabled: true,
    });
  });

  it('cadenceLabel maps known cadences and falls back to the raw value', () => {
    expect(cadenceLabel('daily')).toBe('Diaria');
    expect(cadenceLabel('weekly')).toBe('Semanal');
    expect(cadenceLabel('monthly')).toBe('monthly');
    expect(cadenceLabel(undefined)).toBe('—');
  });

  it('recipientLabel/recipientInitials derive a display label and initials', () => {
    expect(recipientLabel({ recipient_email: 'camila.rojas@acme.co' })).toBe(
      'camila.rojas@acme.co',
    );
    expect(recipientLabel({ recipient_whatsapp: '+573001234567' })).toBe('+573001234567');
    expect(recipientLabel({})).toBe('—');
    expect(recipientInitials({ recipient_email: 'camila.rojas@acme.co' })).toBe('CR');
    expect(recipientInitials({ recipient_email: 'luis@acme.co' })).toBe('LU');
    expect(recipientInitials({})).toBe('··');
  });

  it('formatLastSent returns Nunca for nullish/invalid input', () => {
    expect(formatLastSent(null)).toBe('Nunca');
    expect(formatLastSent('')).toBe('Nunca');
    expect(formatLastSent('not-a-date')).toBe('Nunca');
    expect(formatLastSent('2026-05-14T08:00:00Z')).not.toBe('Nunca');
  });

  it('summarizeSubscriptions counts totals, cadence split and enabled/paused', () => {
    const summary = summarizeSubscriptions([
      { cadence: 'daily', enabled: true },
      { cadence: 'daily', enabled: false },
      { cadence: 'weekly', enabled: true },
    ]);
    expect(summary).toEqual({
      total: 3,
      daily: 2,
      weekly: 1,
      enabled: 2,
      paused: 1,
    });
    expect(summarizeSubscriptions(null)).toEqual({
      total: 0,
      daily: 0,
      weekly: 0,
      enabled: 0,
      paused: 0,
    });
  });
});
