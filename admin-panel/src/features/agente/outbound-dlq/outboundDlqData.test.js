import { describe, it, expect } from 'vitest';

import { errorCodeLabel, formatDate, shortId, totalFailures } from './outboundDlqData.js';

describe('outboundDlqData', () => {
  it('errorCodeLabel maps known Meta codes and falls back to the raw code', () => {
    expect(errorCodeLabel('190')).toBe('Token de acceso caducado');
    expect(errorCodeLabel('131047')).toBe('Fuera de la ventana de 24 h');
    expect(errorCodeLabel('transport')).toBe('Red / timeout');
    expect(errorCodeLabel('99999')).toBe('99999');
    expect(errorCodeLabel('')).toBe('—');
  });

  it('formatDate renders a date or a dash for nullish input', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate('')).toBe('-');
    expect(formatDate('2026-05-14T10:00:00Z')).toMatch(/14\/05/);
  });

  it('shortId truncates to 8 chars + ellipsis', () => {
    expect(shortId('abcdefghijklmnop')).toBe('abcdefgh…');
    expect(shortId(null)).toBe('—');
  });

  it('totalFailures sums the per-error-code counts', () => {
    expect(
      totalFailures([
        { error_code: '190', count: 1 },
        { error_code: '131047', count: 6 },
        { error_code: 'transport', count: 2 },
      ]),
    ).toBe(9);
    expect(totalFailures([])).toBe(0);
    expect(totalFailures(undefined)).toBe(0);
  });
});
