import { describe, it, expect } from 'vitest';

import {
  HEIGHT_MAX_CM,
  HEIGHT_MIN_CM,
  buildBodyPayload,
  silhouetteLabel,
  validateHeight,
} from './step2BodyData.js';


describe('step2BodyData (UI-INFLU-009)', () => {
  it('silhouetteLabel devuelve label en mayúsculas o fallback', () => {
    expect(silhouetteLabel('athletic')).toBe('ATHLETIC');
    expect(silhouetteLabel('curvy')).toBe('CURVY');
    expect(silhouetteLabel(null)).toBe('SIN DEFINIR');
    expect(silhouetteLabel('unknown')).toBe('UNKNOWN');
  });

  it('validateHeight respeta el rango configurado', () => {
    expect(validateHeight(170).valid).toBe(true);
    expect(validateHeight(HEIGHT_MIN_CM).valid).toBe(true);
    expect(validateHeight(HEIGHT_MAX_CM).valid).toBe(true);
    expect(validateHeight(HEIGHT_MIN_CM - 1).valid).toBe(false);
    expect(validateHeight(HEIGHT_MAX_CM + 1).valid).toBe(false);
    expect(validateHeight('abc').valid).toBe(false);
  });

  it('buildBodyPayload aplica defaults sensatos sobre input parcial', () => {
    expect(buildBodyPayload({})).toEqual({
      silhouette: 'average', height_cm: 170, posture: 'confident',
    });
    expect(buildBodyPayload({ silhouette: 'slim', height_cm: '185' })).toEqual({
      silhouette: 'slim', height_cm: 185, posture: 'confident',
    });
  });
});
