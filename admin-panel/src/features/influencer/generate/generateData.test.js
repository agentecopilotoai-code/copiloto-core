import { describe, it, expect } from 'vitest';

import {
  PROMPT_MAX,
  buildGeneratePayload,
  computeCost,
  costExceedsBalance,
  kindMeta,
  promptWithinLimit,
  validateFormatForKind,
} from './generateData.js';


describe('generateData (UI-INFLU-013)', () => {
  it('kindMeta devuelve cost esperado', () => {
    expect(kindMeta('photo').cost).toBe(3);
    expect(kindMeta('reel').cost).toBe(8);
    expect(kindMeta('carousel').cost).toBe(10);
    expect(kindMeta('story').cost).toBe(2);
    expect(kindMeta('ad').cost).toBe(5);
    expect(kindMeta('unknown')).toBeNull();
  });

  it('computeCost escala con count', () => {
    expect(computeCost('photo', 4)).toBe(12);
    expect(computeCost('reel', 2)).toBe(16);
    expect(computeCost('photo', 0)).toBe(3);  // min 1
    expect(computeCost('unknown', 5)).toBe(0);
  });

  it('validateFormatForKind respeta restricciones del kind', () => {
    expect(validateFormatForKind('reel', '9:16')).toBe(true);
    expect(validateFormatForKind('reel', '1:1')).toBe(false);
    expect(validateFormatForKind('photo', '1:1')).toBe(true);
    expect(validateFormatForKind('carousel', '16:9')).toBe(false);
    expect(validateFormatForKind('carousel', '1:1')).toBe(true);
  });

  it('buildGeneratePayload aplica límites + fallback de formato', () => {
    const out = buildGeneratePayload({
      kind: 'reel', prompt: 'x', format: '1:1',  // 1:1 inválido para reel
      count: 100,  // > 10
    });
    expect(out.format).toBe('9:16');  // fallback al primer formato válido
    expect(out.count).toBe(10);  // capeado
  });

  it('promptWithinLimit chequea el max', () => {
    expect(promptWithinLimit('a'.repeat(PROMPT_MAX))).toBe(true);
    expect(promptWithinLimit('a'.repeat(PROMPT_MAX + 1))).toBe(false);
    expect(promptWithinLimit('')).toBe(true);
  });

  it('costExceedsBalance compara cost vs balance', () => {
    expect(costExceedsBalance('photo', 1, 10)).toBe(false);
    expect(costExceedsBalance('reel', 2, 10)).toBe(true);
    expect(costExceedsBalance('photo', 5, 14)).toBe(true);
    expect(costExceedsBalance('photo', 5, 15)).toBe(false);
  });
});
