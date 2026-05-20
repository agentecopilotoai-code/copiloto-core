import { describe, it, expect, vi } from 'vitest';

import {
  DESCRIPTION_MAX,
  buildIdentityPayload,
  debounceHandleCheck,
  descriptionWithinLimit,
  previewCardData,
  validateHandle,
} from './step3IdentityData.js';


describe('step3IdentityData (UI-INFLU-010)', () => {
  it('validateHandle normaliza y aplica regex', () => {
    expect(validateHandle('Sofia_Vega').valid).toBe(true);
    expect(validateHandle('Sofia_Vega').normalized).toBe('sofia_vega');
    expect(validateHandle('').valid).toBe(false);
    expect(validateHandle('ab').valid).toBe(false);
    expect(validateHandle('_starts_with_under').valid).toBe(false);
    expect(validateHandle('with-dash').valid).toBe(false);
    expect(validateHandle('a'.repeat(31)).valid).toBe(false);
  });

  it('buildIdentityPayload trim + límites', () => {
    const out = buildIdentityPayload({
      name: '  Sofía  ', handle: 'SOFIA', age: '25', city: '  Tulum',
      country: 'MX', languages: ['es', 'en', 'fr', 'it', 'pt', 'de', 'ja', 'ko', 'extra'],
      brands: [], categories: ['Lifestyle'],
      description: 'x'.repeat(300),
    });
    expect(out.name).toBe('Sofía');
    expect(out.handle).toBe('sofia');
    expect(out.age).toBe(25);
    expect(out.city).toBe('Tulum');
    expect(out.languages.length).toBe(8);  // capeado
    expect(out.description.length).toBe(DESCRIPTION_MAX);
  });

  it('previewCardData formatea handle + location', () => {
    const out = previewCardData({
      name: 'Sofía', handle: 'sofia', city: 'Tulum', country: 'MX', description: 'hola',
    });
    expect(out.handle).toBe('@sofia');
    expect(out.location).toBe('Tulum, MX');
    expect(out.description).toBe('hola');
  });

  it('debounceHandleCheck llama el callback con delay', async () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const debounced = debounceHandleCheck(fn, 100);
    debounced('a');
    debounced('ab');
    debounced('abc');
    expect(fn).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(150);
    expect(fn).toHaveBeenCalledOnce();
    expect(fn).toHaveBeenCalledWith('abc');
    vi.useRealTimers();
  });

  it('descriptionWithinLimit chequea max chars', () => {
    expect(descriptionWithinLimit('')).toBe(true);
    expect(descriptionWithinLimit('a'.repeat(DESCRIPTION_MAX))).toBe(true);
    expect(descriptionWithinLimit('a'.repeat(DESCRIPTION_MAX + 1))).toBe(false);
  });
});
