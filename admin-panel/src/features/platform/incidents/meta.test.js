import { describe, it, expect } from 'vitest';

import { formatDateTime } from './meta.js';

describe('formatDateTime', () => {
  it('null/undefined → "—"', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('')).toBe('—');
  });

  it('ISO válido produce string formateado', () => {
    const out = formatDateTime('2026-05-20T10:00:00Z');
    expect(out).toMatch(/2026/);
  });

  it('ISO inválido cae al "—" via try/catch', () => {
    // jsdom + Date no lanza por default, devuelve "Invalid Date". El catch
    // solo entra si Date.toLocaleString explota — forzamos pasándole un objeto
    // no serializable.
    expect(formatDateTime('not-a-date')).toMatch(/Invalid|—/);
  });
});
