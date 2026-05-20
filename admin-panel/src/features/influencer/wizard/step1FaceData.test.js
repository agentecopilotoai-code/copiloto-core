import { describe, it, expect } from 'vitest';

import {
  buildFacePayload,
  canonicalFromVariations,
  defaultsForRandom,
  validateMinimum,
} from './step1FaceData.js';


describe('step1FaceData (UI-INFLU-008)', () => {
  it('buildFacePayload omite undefined/null/empty pero conserva los demás', () => {
    const out = buildFacePayload({
      ethnicity: 'latina',
      eye_color: 'brown',
      hair_color: '',
      hair_style: null,
      skin_tone: 'medium',
      age_range: '25-34',
      variations: 4,
      starting_point: 'random',
    });
    expect(out).toEqual({
      ethnicity: 'latina',
      eye_color: 'brown',
      skin_tone: 'medium',
      age_range: '25-34',
      variations: 4,
      starting_point: 'random',
    });
  });

  it('validateMinimum exige etnia + ojos + pelo', () => {
    expect(validateMinimum({}).missing).toEqual(['Etnia', 'Color de ojos', 'Color de pelo']);
    expect(validateMinimum({
      ethnicity: 'latina', eye_color: 'brown', hair_color: 'black',
    }).valid).toBe(true);
    expect(validateMinimum({
      ethnicity: 'latina', eye_color: 'brown',
    }).missing).toEqual(['Color de pelo']);
  });

  it('canonicalFromVariations marca exactamente la variación por id', () => {
    const vars = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    const out = canonicalFromVariations(vars, 'b');
    expect(out.find((v) => v.id === 'a').canonical).toBe(false);
    expect(out.find((v) => v.id === 'b').canonical).toBe(true);
    expect(out.find((v) => v.id === 'c').canonical).toBe(false);
  });

  it('defaultsForRandom devuelve un form completo con starting_point=random', () => {
    const def = defaultsForRandom();
    expect(def.starting_point).toBe('random');
    expect(def.ethnicity).toBeTruthy();
    expect(def.eye_color).toBeTruthy();
    expect(def.hair_color).toBeTruthy();
    expect(def.age_range).toBeTruthy();
    expect(def.variations).toBeGreaterThan(0);
    expect(validateMinimum(def).valid).toBe(true);
  });
});
