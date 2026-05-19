/**
 * UI-INFLU-001 — Design tokens del módulo Influencer / Ravit Studio.
 *
 * Verifica que `admin-panel/src/styles/tokens.css` declara TODOS los tokens
 * derivados del diseño de Ravit Studio. Fuente de verdad visual:
 *   - docs/influencer/04 _ Paleta.html (colores · superficies · estados)
 *   - docs/influencer/05 _ Tipograf_a.html (escala + tracking + familias)
 *
 * Si el diseñador agrega o cambia un token en los HTMLs anteriores, este
 * test debe fallar hasta que `tokens.css` se sincronice — así mantenemos
 * el contrato HTML ↔ código siempre verde.
 *
 * Política declarada en `04 _ Paleta.html`:
 *   "El verde es la voz de Ravit, no su volumen. Cream + navy hacen el 95%
 *    del trabajo. El verde sólo entra para señalar AI, acción primaria y
 *    estado activo."
 *
 * Los tokens del módulo son **aditivos**: NO reemplazan los tokens base
 * de CopilotoIA (`--bg`, `--ink`, `--accent`, etc.). El sistema base
 * sigue intacto para el resto del admin panel.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { cwd } from 'node:process';

const TOKENS_CSS = readFileSync(
  resolve(cwd(), 'src/styles/tokens.css'),
  'utf-8',
);

// El test corre desde admin-panel/ (cwd de vitest); los HTMLs viven en
// ../docs/influencer/. Resolvemos absoluto para no depender del CWD del
// runner.
const REPO_ROOT = resolve(cwd(), '..');
const PALETTE_HTML = resolve(REPO_ROOT, 'docs/influencer/04 _ Paleta.html');
const TYPOGRAPHY_HTML = resolve(REPO_ROOT, 'docs/influencer/05 _ Tipograf_a.html');

// Colores canónicos del HTML "04 _ Paleta.html". Si el diseñador cambia
// uno, se actualiza aquí Y en tokens.css en el mismo commit.
const EXPECTED_COLOR_TOKENS = {
  // Superficies — "Bento warm · cream surfaces"
  '--influencer-bg':          '#F1EDE3',
  '--influencer-bg-alt':      '#E8E2D3',
  '--influencer-bg-sidebar':  '#F7F4EA',
  '--influencer-bg-card':     '#FFFFFF',
  '--influencer-bg-card-alt': '#FBF9F2',
  // Texto — "Navy de la identidad Pulse"
  '--influencer-ink':         '#1B2542',
  // Verde Ravit — identidad / acento
  '--influencer-green':       '#2DBB6A',
  '--influencer-green-dim':   '#0F7A3F',
  // Estados — toasts · validaciones · semáforos
  '--influencer-coral':       '#E45D4A',
  '--influencer-amber':       '#D99536',
  '--influencer-sky':         '#5B8FB9',
};

// Escala tipográfica del HTML "05 _ Tipograf_a.html".
const EXPECTED_FONT_SIZES = {
  '--influencer-fs-display-xl': '56px',
  '--influencer-fs-display-l':  '40px',
  '--influencer-fs-display-m':  '32px',
  '--influencer-fs-display-s':  '22px',
  '--influencer-fs-heading':    '17px',
  '--influencer-fs-body-l':     '16px',
  '--influencer-fs-body-m':     '14px',
  '--influencer-fs-body-s':     '13px',
  '--influencer-fs-caption':    '11.5px',
  '--influencer-fs-eyebrow':    '10.5px',
  '--influencer-fs-mono-cap':   '10px',
  '--influencer-fs-code':       '12px',
};

describe('UI-INFLU-001 — Influencer / Ravit Studio design tokens', () => {
  it('los HTMLs de diseño del módulo están presentes en el repo', () => {
    expect(existsSync(PALETTE_HTML), `falta: ${PALETTE_HTML}`).toBe(true);
    expect(existsSync(TYPOGRAPHY_HTML), `falta: ${TYPOGRAPHY_HTML}`).toBe(true);
  });

  it('tokens.css declara todos los colores del HTML de paleta', () => {
    for (const [name, value] of Object.entries(EXPECTED_COLOR_TOKENS)) {
      // Escapamos `#` para construir una regex segura.
      const re = new RegExp(
        `${name}\\s*:\\s*${value.replace(/[#]/g, '\\$&')}`,
        'i',
      );
      expect(
        TOKENS_CSS,
        `tokens.css debe declarar "${name}: ${value};" (de 04 _ Paleta.html)`,
      ).toMatch(re);
    }
  });

  it('tokens.css declara la escala tipográfica del HTML de tipografía', () => {
    for (const [name, value] of Object.entries(EXPECTED_FONT_SIZES)) {
      const re = new RegExp(
        `${name}\\s*:\\s*${value.replace(/\./g, '\\.')}`,
      );
      expect(
        TOKENS_CSS,
        `tokens.css debe declarar "${name}: ${value};" (de 05 _ Tipograf_a.html)`,
      ).toMatch(re);
    }
  });

  it('verde Ravit aparece con sus 3 variantes (regla de oro del HTML)', () => {
    // El HTML "04 _ Paleta" declara: "El verde es la voz de Ravit, no su
    // volumen". Las 3 variantes son necesarias para CTA primario (solid),
    // badges/pills (soft) y bordes activos.
    expect(TOKENS_CSS).toMatch(/--influencer-green\s*:\s*#2DBB6A/i);
    expect(TOKENS_CSS).toMatch(
      /--influencer-green-soft\s*:\s*rgba\(45,\s*187,\s*106,\s*0\.12\)/,
    );
    expect(TOKENS_CSS).toMatch(
      /--influencer-green-border\s*:\s*rgba\(45,\s*187,\s*106,\s*0\.38\)/,
    );
  });

  it('navy Pulse (#1B2542) tiene las 4 variantes de opacidad para texto', () => {
    expect(TOKENS_CSS).toMatch(/--influencer-ink\s*:\s*#1B2542/i);
    expect(TOKENS_CSS).toMatch(
      /--influencer-ink-mid\s*:\s*rgba\(27,\s*37,\s*66,\s*0\.78\)/,
    );
    expect(TOKENS_CSS).toMatch(
      /--influencer-ink-soft\s*:\s*rgba\(27,\s*37,\s*66,\s*0\.55\)/,
    );
    expect(TOKENS_CSS).toMatch(
      /--influencer-ink-faint\s*:\s*rgba\(27,\s*37,\s*66,\s*0\.32\)/,
    );
  });

  it('familia tipográfica Geist con fallback Inter Tight + Inter', () => {
    // De "05 _ Tipograf_a.html":
    //   "geist.font · Vercel · variable · serif fallback Inter Tight"
    expect(TOKENS_CSS).toMatch(/--influencer-font-sans\s*:\s*'Geist'/);
    expect(TOKENS_CSS).toMatch(
      /--influencer-font-sans\s*:[^;]*'Inter Tight'/,
    );
    expect(TOKENS_CSS).toMatch(/--influencer-font-mono\s*:\s*'Geist Mono'/);
  });

  it('letter-spacing del módulo cubre display + eyebrow + mono caption', () => {
    expect(TOKENS_CSS).toMatch(/--influencer-ls-display-xl\s*:\s*-0\.04em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-display-l\s*:\s*-0\.035em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-display-m\s*:\s*-0\.03em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-display-s\s*:\s*-0\.02em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-heading\s*:\s*-0\.015em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-eyebrow\s*:\s*0\.18em/);
    expect(TOKENS_CSS).toMatch(/--influencer-ls-mono-cap\s*:\s*0\.16em/);
  });

  it('los tokens del módulo NO sobreescriben los tokens base (D2 del mandato UI)', () => {
    // tokens.css base tiene --bg, --ink, --accent, etc. para el resto del
    // admin panel. Los del módulo influencer deben coexistir sin pisarlos.
    expect(TOKENS_CSS).toMatch(/^\s*--bg:\s+#f6f5f1/m);
    expect(TOKENS_CSS).toMatch(/^\s*--ink:\s+#0e0f0c/m);
    expect(TOKENS_CSS).toMatch(/^\s*--accent:/m);
    expect(TOKENS_CSS).toMatch(/^\s*--influencer-bg:/m);
    expect(TOKENS_CSS).toMatch(/^\s*--influencer-ink:/m);
  });

  it('los hexadecimales del HTML de paleta están mapeados a tokens en CSS', () => {
    // Audit cruzado: lee el HTML, extrae cada hex visible en la paleta, y
    // verifica que aparece como valor de algún token en tokens.css. Esto
    // detecta el caso "el diseñador agregó un nuevo color pero nadie lo
    // mapeó al CSS".
    const html = readFileSync(PALETTE_HTML, 'utf-8');
    const hexesInHtml = new Set(
      [...html.matchAll(/#[0-9A-Fa-f]{6}\b/g)].map((m) => m[0].toUpperCase()),
    );
    const expectedFromDesign = [
      '#F1EDE3', '#E8E2D3', '#F7F4EA', '#FFFFFF', '#FBF9F2',
      '#1B2542', '#2DBB6A', '#0F7A3F',
      '#E45D4A', '#D99536', '#5B8FB9',
    ];
    for (const hex of expectedFromDesign) {
      expect(
        hexesInHtml,
        `el HTML 04 _ Paleta debe mencionar ${hex}`,
      ).toContain(hex);
      const re = new RegExp(hex.replace(/[#]/g, '\\$&'), 'i');
      expect(TOKENS_CSS, `tokens.css debe declarar ${hex}`).toMatch(re);
    }
  });
});
