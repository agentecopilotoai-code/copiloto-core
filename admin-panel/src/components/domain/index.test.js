import { describe, it, expect } from 'vitest';

import * as domain from './index.js';

describe('components/domain/index.js — barrel re-exports', () => {
  it('expone los componentes y helpers transversales del core', () => {
    expect(typeof domain.KpiCardWithDelta).toBe('function');
    expect(typeof domain.computeDelta).toBe('function');
    expect(typeof domain.MfaRequiredBlocker).toBe('function');
    expect(typeof domain.NoTenantOnboarding).toBe('function');
    expect(typeof domain.SupportModeBanner).toBe('function');
  });
});
