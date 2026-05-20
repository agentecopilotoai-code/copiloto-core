/**
 * UI-INFLU-008 — Helpers puros para el paso 1 del wizard (Cara).
 */

export const FACE_OPTIONS = {
  ethnicity: [
    'europea', 'asiática', 'africana', 'latina', 'oriente medio', 'caribeña',
  ],
  eye_color: ['brown', 'black', 'blue', 'green', 'hazel', 'gray', 'amber'],
  hair_color: ['black', 'brown', 'blonde', 'red', 'gray', 'white', 'colored'],
  hair_style: ['short', 'medium', 'long', 'curly', 'wavy', 'straight', 'shaved'],
  skin_tone: ['light', 'medium-light', 'medium', 'medium-dark', 'dark'],
  age_range: ['18-24', '25-34', '35-44', '45-54', '55+'],
};


export function defaultsForRandom() {
  return {
    starting_point: 'random',
    ethnicity: 'latina',
    eye_color: 'brown',
    hair_color: 'black',
    hair_style: 'long',
    skin_tone: 'medium',
    age_range: '25-34',
    variations: 4,
  };
}


/**
 * Valida que el formulario tenga los campos mínimos para generar
 * variaciones. Devuelve `{valid, missing[]}` para que el UI muestre
 * un AlertBanner con la lista.
 */
export function validateMinimum(form) {
  const missing = [];
  if (!form?.ethnicity) missing.push('Etnia');
  if (!form?.eye_color) missing.push('Color de ojos');
  if (!form?.hair_color) missing.push('Color de pelo');
  return { valid: missing.length === 0, missing };
}


/**
 * Construye el payload del PUT /personas/{id}/face a partir del estado
 * del formulario. Omite campos nulos para no sobreescribir con vacío.
 */
export function buildFacePayload(form) {
  const payload = {};
  for (const key of [
    'starting_point', 'ethnicity', 'eye_color', 'hair_color',
    'hair_style', 'skin_tone', 'age_range', 'variations',
  ]) {
    if (form?.[key] !== undefined && form?.[key] !== null && form?.[key] !== '') {
      payload[key] = form[key];
    }
  }
  return payload;
}


/**
 * Marca una variación como canonical y devuelve la lista actualizada.
 */
export function canonicalFromVariations(variations, canonicalId) {
  if (!Array.isArray(variations)) return [];
  return variations.map((v) => ({ ...v, canonical: v.id === canonicalId }));
}
