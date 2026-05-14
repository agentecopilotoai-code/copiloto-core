import { describe, it, expect } from 'vitest';

import { ONBOARDING_STEPS, ONBOARDING_TOTAL_STEPS, stepStatus } from './onboardingSteps.js';

describe('onboardingSteps', () => {
  it('declares the 7-step TASK-0069 catalogue', () => {
    expect(ONBOARDING_STEPS).toHaveLength(7);
    expect(ONBOARDING_TOTAL_STEPS).toBe(7);
    expect(ONBOARDING_STEPS.map((s) => s.step)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    for (const step of ONBOARDING_STEPS) {
      expect(step).toHaveProperty('key');
      expect(step).toHaveProperty('label');
      expect(step).toHaveProperty('helper');
    }
  });

  it('stepStatus marks completed steps done, the next step current, the rest blocked', () => {
    // nothing completed yet
    expect(stepStatus(1, 0)).toBe('current');
    expect(stepStatus(2, 0)).toBe('blocked');
    // 3 steps completed
    expect(stepStatus(2, 3)).toBe('done');
    expect(stepStatus(3, 3)).toBe('done');
    expect(stepStatus(4, 3)).toBe('current');
    expect(stepStatus(5, 3)).toBe('blocked');
    // all done
    expect(stepStatus(7, 7)).toBe('done');
  });

  it('stepStatus tolerates a missing / nullish lastCompleted', () => {
    expect(stepStatus(1, undefined)).toBe('current');
    expect(stepStatus(1, null)).toBe('current');
  });
});
