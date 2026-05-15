import '@testing-library/jest-dom/vitest';
import * as axeMatchers from 'vitest-axe/matchers';
import { expect } from 'vitest';

// UI-013 — habilita `expect(...).toHaveNoViolations()` y similares de axe-core
// para los smokes de accesibilidad bajo `src/__tests__/a11y/`.
expect.extend(axeMatchers);
