import { describe, it, expect } from 'vitest';

import {
  formatMoney,
  formatMrrByCurrency,
  formatPercent,
  sortByMrrDesc,
} from './format.js';

describe('formatMoney', () => {
  it('formatea con currency válida', () => {
    expect(formatMoney(1000, 'USD')).toMatch(/USD|US\$/);
  });

  it('handlea null/NaN como 0', () => {
    expect(formatMoney(null, 'COP')).toMatch(/0/);
    expect(formatMoney('not a number', 'COP')).toMatch(/0/);
  });

  it('fallback cuando Intl rechaza la currency', () => {
    const out = formatMoney(100, 'NOT_A_CURRENCY');
    expect(out).toMatch(/100/);
  });

  it('currency vacío usa COP default', () => {
    expect(formatMoney(50)).toMatch(/50/);
  });
});

describe('formatPercent', () => {
  it('null/undefined → "—"', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(undefined)).toBe('—');
  });

  it('multiplica por 100 con 1 decimal', () => {
    expect(formatPercent(0.155)).toBe('15.5%');
    expect(formatPercent(0)).toBe('0.0%');
  });
});

describe('sortByMrrDesc', () => {
  it('ordena por mrr descendente sin mutar', () => {
    const input = [{ mrr: 1 }, { mrr: 5 }, { mrr: 3 }];
    const out = sortByMrrDesc(input);
    expect(out.map((x) => x.mrr)).toEqual([5, 3, 1]);
    expect(input.map((x) => x.mrr)).toEqual([1, 5, 3]); // sin mutar
  });

  it('null/empty no explota', () => {
    expect(sortByMrrDesc(null)).toEqual([]);
    expect(sortByMrrDesc([])).toEqual([]);
  });

  it('entries sin mrr cuentan como 0', () => {
    expect(sortByMrrDesc([{ x: 1 }, { mrr: 5 }])[0].mrr).toBe(5);
  });
});

describe('formatMrrByCurrency', () => {
  it('vacío → "—"', () => {
    expect(formatMrrByCurrency([])).toBe('—');
    expect(formatMrrByCurrency(null)).toBe('—');
  });

  it('joins por " · "', () => {
    const out = formatMrrByCurrency([
      { currency: 'COP', mrr: 580 },
      { currency: 'USD', mrr: 50 },
    ]);
    expect(out).toMatch(/COP|580/);
    expect(out).toContain('·');
  });
});
