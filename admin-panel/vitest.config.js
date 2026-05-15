import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
    css: {
      modules: {
        classNameStrategy: 'non-scoped',
      },
    },
    include: ['src/**/*.test.{js,jsx}'],
    // UI-014 — Cobertura del admin-panel.
    // Mínimos por directorio:
    //   - components/ui   ≥ 60%
    //   - permissions     ≥ 60%
    //   - features        ≥ 40%
    // El job de CI corre `npm run test:coverage` y falla si algún umbral
    // queda por debajo. Mantener estos números en sincronía con
    // docs/UI_BACKLOG.md (UI-014) y docs/DONE.md.
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,jsx}'],
      exclude: [
        'src/**/*.test.{js,jsx}',
        'src/**/__tests__/**',
        'src/main.jsx',
        'src/**/*.module.css',
      ],
      thresholds: {
        'src/components/ui/**': {
          lines: 60,
          functions: 60,
          branches: 60,
          statements: 60,
        },
        'src/permissions/**': {
          lines: 60,
          functions: 60,
          branches: 60,
          statements: 60,
        },
        'src/features/**': {
          lines: 40,
          functions: 40,
          branches: 40,
          statements: 40,
        },
      },
    },
  },
});
