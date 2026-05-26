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
    // Cobertura del admin-panel — branch `core`.
    //
    // **Estado actual: 98.6% líneas, 85% branches, 91% funcs** (550+ tests).
    // El umbral global PR-merge se subió a 98% después de la purga total
    // del core (commit "feat(core): admin-panel coverage push to 98%+").
    // Las thresholds por carpeta son aún más estrictas donde ya tenemos
    // cobertura cerca de 100%.
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,jsx}'],
      exclude: [
        'src/**/*.test.{js,jsx}',
        'src/**/__tests__/**',
        'src/main.jsx',
        'src/**/*.module.css',
      ],
      thresholds: {
        // Umbrales globales — bloquean regresiones puntuales del estado
        // actual del core.
        lines: 98,
        statements: 98,
        functions: 90,
        branches: 84,
        // Umbrales por carpeta — más estrictos donde la cobertura es ~100%.
        'src/components/ui/**': {
          lines: 95,
          functions: 85,
          branches: 85,
          statements: 95,
        },
        'src/permissions/**': {
          lines: 95,
          functions: 85,
          branches: 90,
          statements: 95,
        },
        'src/services/**': {
          lines: 98,
          functions: 95,
          branches: 90,
          statements: 98,
        },
        'src/hooks/**': {
          lines: 95,
          functions: 85,
          branches: 80,
          statements: 95,
        },
        'src/features/**': {
          lines: 97,
          functions: 80,
          branches: 75,
          statements: 97,
        },
      },
    },
  },
});
