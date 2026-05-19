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
    // Cobertura del admin-panel.
    // **Umbral global: ≥85%** statements/lines (política PR-merge).
    //   - Si el total cae bajo 85%, `npm run test:coverage` exit 1 → CI rojo
    //     → branch protection bloquea el merge.
    //   - Mantener este número alineado con docs/DONE.md y la regla de
    //     `Required status checks` en GitHub.
    //
    // Mínimos por directorio (más estrictos donde ya tenemos cobertura
    // alta, para evitar regresiones puntuales aun cuando el total siga ≥85%):
    //   - components/ui    ≥ 85%
    //   - permissions      ≥ 85%
    //   - services         ≥ 85%
    //   - hooks            ≥ 85%
    //   - features         ≥ 80% (todavía hay sub-módulos en construcción)
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
        // Umbral global — el más importante para la regla "PR no mergeable
        // si frontend coverage < 85%".
        lines: 85,
        statements: 85,
        functions: 75,
        branches: 75,
        // Umbrales por carpeta — más estrictos donde ya hay cobertura alta
        // y deben preservarse.
        'src/components/ui/**': {
          lines: 85,
          functions: 75,
          branches: 75,
          statements: 85,
        },
        'src/permissions/**': {
          lines: 85,
          functions: 75,
          branches: 75,
          statements: 85,
        },
        'src/services/**': {
          lines: 85,
          functions: 75,
          branches: 75,
          statements: 85,
        },
        'src/hooks/**': {
          lines: 85,
          functions: 75,
          branches: 75,
          statements: 85,
        },
        'src/features/**': {
          lines: 80,
          functions: 70,
          branches: 70,
          statements: 80,
        },
      },
    },
  },
});
