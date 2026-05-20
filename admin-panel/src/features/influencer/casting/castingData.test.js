import { describe, it, expect } from 'vitest';

import {
  categoryLabel,
  filterByCategory,
  formatEngagementRate,
  formatReach,
  sortPersonas,
} from './castingData.js';


describe('castingData helpers', () => {
  it('categoryLabel mapea ids a labels en español y fallback', () => {
    expect(categoryLabel('lifestyle')).toBe('Lifestyle');
    expect(categoryLabel('FASHION')).toBe('Fashion');
    expect(categoryLabel(null)).toBe('Sin categoría');
    expect(categoryLabel('unknown_cat')).toBe('unknown_cat');
  });

  it('formatReach humaniza miles y millones', () => {
    expect(formatReach(250)).toBe('250');
    expect(formatReach(3500)).toBe('3.5K');
    expect(formatReach(12000)).toBe('12K');
    expect(formatReach(2_400_000)).toBe('2.4M');
    expect(formatReach(0)).toBe('0');
  });

  it('formatEngagementRate acepta proporción (0..1) y pct (0..100)', () => {
    expect(formatEngagementRate(0.057)).toBe('5.7%');
    expect(formatEngagementRate(5.7)).toBe('5.7%');  // > 1 → ya pct
    expect(formatEngagementRate(0)).toBe('0.0%');
    expect(formatEngagementRate('not a number')).toBe('0%');
  });

  it('sortPersonas ordena por cada criterio', () => {
    const personas = [
      { id: '1', engagement_rate: 0.02, posts_total: 30, reach_30d: 100 },
      { id: '2', engagement_rate: 0.05, posts_total: 10, reach_30d: 500 },
      { id: '3', engagement_rate: 0.01, posts_total: 50, reach_30d: 50 },
    ];
    expect(sortPersonas(personas, 'activity').map((p) => p.id)).toEqual(['2', '1', '3']);
    expect(sortPersonas(personas, 'posts').map((p) => p.id)).toEqual(['3', '1', '2']);
    expect(sortPersonas(personas, 'reach').map((p) => p.id)).toEqual(['2', '1', '3']);
    // Criterio desconocido preserva orden
    expect(sortPersonas(personas, 'wat').map((p) => p.id)).toEqual(['1', '2', '3']);
  });

  it('filterByCategory respeta la categoría seleccionada (case-insensitive)', () => {
    const personas = [
      { id: '1', category: 'fashion' },
      { id: '2', category: 'Beauty' },
      { id: '3', category: 'fashion' },
    ];
    expect(filterByCategory(personas, null).length).toBe(3);
    expect(filterByCategory(personas, 'fashion').map((p) => p.id)).toEqual(['1', '3']);
    expect(filterByCategory(personas, 'BEAUTY').map((p) => p.id)).toEqual(['2']);
    expect(filterByCategory(personas, 'unknown').length).toBe(0);
  });
});
