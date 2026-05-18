/**
 * BUG-014 — los placeholders del wizard de WhatsApp NO deben parecer valores
 * reales pre-cargados.
 *
 * Síntoma observado en runtime (2026-05-17): un platform_owner crea un tenant
 * nuevo y va a "Configurar WhatsApp". El form muestra `1154501041071506`
 * en el "Phone Number ID" — pero NADA se guardó en ese tenant todavía. El
 * usuario asume que es un valor leakeado de otro tenant, intenta borrarlo,
 * etc. En realidad es el `placeholder` HTML del input (texto gris cuando el
 * field está vacío) pero los números largos secuenciales `123456789012345`,
 * `987654321098765`, `112233445566778` son indistinguibles visualmente de
 * valores reales — sobre todo en monitores de bajo contraste o si el usuario
 * tiene CSS dark-mode que no atenúa lo suficiente el color del placeholder.
 *
 * Fix: cambiar los placeholders por texto descriptivo SIN números largos
 * que parezcan datos reales. Cualquier indicación de "ID numérico" + tipo
 * funciona — el placeholder ya no se confunde con un valor.
 *
 * Anti-regression: este test prohibe placeholders que sean solo dígitos en
 * el wizard. Si alguien re-introduce `placeholder="123456789012345"`, el
 * test falla loudly antes de prod.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WIZARD_FILE = resolve(__dirname, 'WhatsAppWizardSteps.jsx');

describe('BUG-014 — WhatsApp wizard placeholders', () => {
  const source = readFileSync(WIZARD_FILE, 'utf8');

  it('no tiene placeholders puramente numéricos largos (≥6 dígitos) que parezcan IDs reales', () => {
    // Captura cualquier `placeholder="<digits-only>"` con 6+ digits.
    // 6 es el umbral porque IDs cortos como "12345" no se confunden con
    // datos reales, pero `123456789012345` sí.
    const purelyNumericLong = /placeholder="\d{6,}"/g;
    const matches = source.match(purelyNumericLong) || [];
    expect(matches).toEqual([]);
  });

  it('todos los placeholders de IDs (business/waba/phone) incluyen texto descriptivo', () => {
    // Para cada uno de los 3 campos críticos, el placeholder debe tener al
    // menos UN caracter alfabético (letra). Eso asegura que el placeholder
    // es texto descriptivo, no puro número.
    const fields = ['business_id', 'waba_id', 'phone_number_id'];
    for (const field of fields) {
      // Busca el bloque <input onChange={set('FIELD')} ... placeholder="..."/>.
      const setPattern = new RegExp(
        `set\\('${field}'\\)[\\s\\S]{0,500}?placeholder="([^"]*)"`,
        'm',
      );
      const match = source.match(setPattern);
      expect(match, `no se encontró placeholder para ${field}`).not.toBeNull();
      const placeholder = match[1];
      const hasAlpha = /[a-zA-Záéíóúñü]/i.test(placeholder);
      expect(
        hasAlpha,
        `placeholder de ${field} ("${placeholder}") es puramente numérico — `
          + 'usar texto descriptivo (ej. "ID numérico de ...") para que el usuario '
          + 'no lo confunda con un valor pre-cargado.',
      ).toBe(true);
    }
  });

  it('placeholders prohibidos específicos del bug original NO regresan', () => {
    // Los 3 valores exactos que el usuario reportó / que estaban en el código
    // antes del fix. Si alguien revierte el fix, este test falla con un
    // mensaje específico que linkea al bug.
    const forbidden = [
      '123456789012345',
      '987654321098765',
      '112233445566778',
    ];
    for (const value of forbidden) {
      expect(
        source.includes(`placeholder="${value}"`),
        `BUG-014 regression: placeholder "${value}" reintroducido — usar texto descriptivo.`,
      ).toBe(false);
    }
  });
});
