/**
 * BUG-018 — anti-regression del layout del workspace.
 *
 * Síntoma observado en runtime (2026-05-17):
 *   Cuando el platform_owner opera bajo support_mode (banner naranja
 *   visible) y entra a módulos como `/admin/t/{slug}/my-handoffs`,
 *   `/admin/t/{slug}/campaigns` o `/admin/t/{slug}/digest`, el
 *   ShellTopbar aparece como un card blanco gigante ocupando casi
 *   toda la pantalla con el título "Tenant Operations / <Módulo>"
 *   flotando en el medio del vacío. El contenido real del módulo
 *   queda apretado al fondo.
 *
 * Root cause:
 *   `.workspace { display: grid; grid-template-rows: auto 1fr }` con 3
 *   children (SupportModeBanner + ShellTopbar + ErrorBoundary). El item
 *   2 (ShellTopbar) caía en el row `1fr` y se estiraba para llenar
 *   todo el espacio disponible.
 *
 * Fix:
 *   `.workspace { display: flex; flex-direction: column; gap: ... }`.
 *   Flex column normal NO estira items por default (a diferencia de
 *   grid `1fr`). Todos quedan compactos arriba.
 *
 * Si alguien revierte el CSS a grid sin pensar, este test falla.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SHELL_CSS = resolve(__dirname, 'shell.module.css');

describe('BUG-018 — shell workspace layout', () => {
  const source = readFileSync(SHELL_CSS, 'utf8');

  it('workspace usa display:flex, NO display:grid con 1fr', () => {
    // Extrae el bloque `.workspace { ... }` (hasta el próximo selector).
    const workspaceBlockMatch = source.match(/\.workspace\s*\{([^}]+)\}/);
    expect(workspaceBlockMatch, '.workspace selector no existe').not.toBeNull();
    const block = workspaceBlockMatch[1];

    // El fix: display debe ser flex (no grid). Grid con 1fr es justo lo que
    // causaba el bug — el segundo item se estiraba cuando había 3+ children.
    expect(
      block,
      'BUG-018 regression: .workspace volvió a usar grid + 1fr. Eso estira '
        + 'el ShellTopbar cuando hay SupportModeBanner visible. Usar '
        + 'display:flex; flex-direction:column.',
    ).toMatch(/display:\s*flex/);
    expect(block).not.toMatch(/display:\s*grid/);
    // Específicamente prohibir el patrón roto.
    expect(
      block,
      'BUG-018 regression: grid-template-rows: auto 1fr re-introducido. '
        + 'Con 3+ children, el item 2 cae en 1fr y se estira creando el '
        + 'espacio blanco gigante del bug.',
    ).not.toMatch(/grid-template-rows:\s*auto\s+1fr/);
  });

  it('workspace tiene flex-direction column (los items se apilan verticalmente)', () => {
    const workspaceBlockMatch = source.match(/\.workspace\s*\{([^}]+)\}/);
    const block = workspaceBlockMatch[1];
    expect(block).toMatch(/flex-direction:\s*column/);
  });

  it('workspace preserva gap entre items y min-height del viewport', () => {
    const workspaceBlockMatch = source.match(/\.workspace\s*\{([^}]+)\}/);
    const block = workspaceBlockMatch[1];
    // El gap separa SupportModeBanner, ShellTopbar y el contenido del módulo.
    expect(block).toMatch(/gap:\s*var\(--space-/);
    // min-height 100% mantiene el footprint del shell aunque el módulo
    // tenga poco contenido (sin esto el shell se colapsa visualmente).
    expect(block).toMatch(/min-height:\s*100%/);
  });

  it('workspace mantiene min-width:0 (defensa contra overflow horizontal)', () => {
    // Sin esto, flex/grid children con `min-content: auto` (default)
    // pueden empujar el ancho del workspace más allá del viewport,
    // sacando la sidebar de cuadro en mobile.
    const workspaceBlockMatch = source.match(/\.workspace\s*\{([^}]+)\}/);
    const block = workspaceBlockMatch[1];
    expect(block).toMatch(/min-width:\s*0/);
  });

  it('BUG-018 doc anchor: el comentario del fix menciona BUG-018', () => {
    // Anti "limpieza descuidada": un futuro PR que refactorice el CSS sin
    // entender el motivo debería ver el comentario que linkea al ticket.
    expect(source).toMatch(/BUG-018/);
  });
});
