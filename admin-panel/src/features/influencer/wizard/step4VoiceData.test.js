import { describe, it, expect } from 'vitest';

import {
  buildVoicePayload,
  captionPromptHash,
  toneLabel,
  validateMinimum,
} from './step4VoiceData.js';


describe('step4VoiceData (UI-INFLU-011)', () => {
  it('toneLabel mapea valores conocidos y capitaliza fallback', () => {
    expect(toneLabel('warm')).toBe('Cálida');
    expect(toneLabel('professional')).toBe('Profesional');
    expect(toneLabel(null)).toBe('Sin definir');
    expect(toneLabel('other')).toBe('Other');
  });

  it('buildVoicePayload aplica clamp en energy_level y defaults', () => {
    expect(buildVoicePayload({}).energy_level).toBe(5);
    expect(buildVoicePayload({ energy_level: 50 }).energy_level).toBe(10);
    expect(buildVoicePayload({ energy_level: -5 }).energy_level).toBe(1);
    expect(buildVoicePayload({}).tone).toBe('warm');
    expect(buildVoicePayload({ tone: 'close' }).tone).toBe('close');
  });

  it('captionPromptHash es estable para los mismos inputs y distinto para cambios', () => {
    const a = captionPromptHash({ tone: 'warm', formality: 'informal', energy_level: 5 });
    const b = captionPromptHash({ tone: 'warm', formality: 'informal', energy_level: 5 });
    expect(a).toBe(b);
    const c = captionPromptHash({ tone: 'close', formality: 'informal', energy_level: 5 });
    expect(a).not.toBe(c);
  });

  it('validateMinimum exige tone', () => {
    expect(validateMinimum({}).valid).toBe(false);
    expect(validateMinimum({ tone: 'warm' }).valid).toBe(true);
  });
});
