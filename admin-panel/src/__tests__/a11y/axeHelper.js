/**
 * Helper compartido por los smokes de accesibilidad (UI-013).
 *
 * - Configura axe-core para reportar SOLO violaciones de impacto `serious` o
 *   `critical`. Las de impacto `moderate` / `minor` quedan fuera del smoke
 *   pero pueden ser auditadas manualmente y entran como follow-up.
 * - Deshabilita reglas que axe-core no puede evaluar bien dentro de jsdom o
 *   que generan ruido en componentes desconectados de la app real:
 *     · `region` — los smokes montan vistas individuales fuera del shell, por
 *        lo que no siempre existe el landmark `<main>` que la regla exige.
 *     · `color-contrast` — axe-core no puede calcular contraste real en jsdom
 *        (no layout / no rendering). El contraste real se valida en CI visual.
 *
 * Uso:
 *   import { runAxe } from '../axeHelper.js';
 *   const { container } = render(<View/>);
 *   expect(await runAxe(container)).toHaveNoViolations();
 */
import { configureAxe } from 'vitest-axe';

const baseAxe = configureAxe({
  rules: {
    region: { enabled: false },
    'color-contrast': { enabled: false },
  },
});

const BLOCKING_IMPACT = new Set(['serious', 'critical']);

/**
 * Ejecuta axe-core sobre `container` y devuelve un resultado en el que sólo
 * permanecen las violaciones con impacto `serious` o `critical`. El matcher
 * `toHaveNoViolations()` pasa si y sólo si esa lista filtrada está vacía.
 */
export async function runAxe(container) {
  const results = await baseAxe(container);
  return {
    ...results,
    violations: results.violations.filter(
      (violation) => BLOCKING_IMPACT.has(violation.impact),
    ),
  };
}
