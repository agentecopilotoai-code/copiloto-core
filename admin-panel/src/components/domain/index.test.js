import { describe, it, expect } from 'vitest';

import * as domain from './index.js';

describe('components/domain/index.js — barrel re-exports', () => {
  it('expone los componentes transversales del core', () => {
    expect(typeof domain.NoTenantOnboarding).toBe('function');
    expect(typeof domain.SupportModeBanner).toBe('function');
  });
});
