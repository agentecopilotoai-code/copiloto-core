import { describe, it, expect } from 'vitest';

import {
  cadenceToPerWeek,
  cannotDisableDiscloseAi,
  computeWeeklyCredits,
  modeLabel,
  validateAtLeastOnePlatform,
} from './step5PlatformsData.js';


describe('step5PlatformsData (UI-INFLU-012)', () => {
  it('cadenceToPerWeek soporta presets y números', () => {
    expect(cadenceToPerWeek('daily')).toBe(7);
    expect(cadenceToPerWeek('5_week')).toBe(5);
    expect(cadenceToPerWeek(3)).toBe(3);
    expect(cadenceToPerWeek('unknown')).toBe(0);  // fallback a 0 cuando no parsea
  });

  it('computeWeeklyCredits suma posts/sem * costo', () => {
    const accounts = [
      { platform: 'instagram', posts_per_week: 5, primary_kind: 'photo' },
      { platform: 'tiktok', posts_per_week: 3, primary_kind: 'reel' },
    ];
    // photo=3, reel=8
    // ig: 5*3=15, tt: 3*8=24 → 39
    expect(computeWeeklyCredits(accounts)).toBe(39);
    // Custom pricing
    expect(computeWeeklyCredits(accounts, { photo: 2, reel: 10 })).toBe(40);
  });

  it('validateAtLeastOnePlatform exige handle no vacío', () => {
    expect(validateAtLeastOnePlatform([])).toBe(false);
    expect(validateAtLeastOnePlatform([{ platform: 'ig', handle: '' }])).toBe(false);
    expect(validateAtLeastOnePlatform([{ platform: 'ig', handle: '@s' }])).toBe(true);
  });

  it('modeLabel devuelve label español', () => {
    expect(modeLabel('auto_generate')).toBe('Auto-generar contenido');
    expect(modeLabel('manual_approval')).toBe('Aprobación manual');
    expect(modeLabel('hybrid')).toBe('Híbrido');
    expect(modeLabel('unknown')).toBe('unknown');
  });

  it('cannotDisableDiscloseAi siempre devuelve true', () => {
    expect(cannotDisableDiscloseAi()).toBe(true);
  });
});
