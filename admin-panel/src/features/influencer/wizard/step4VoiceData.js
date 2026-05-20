/**
 * UI-INFLU-011 — Helpers puros para el paso 4 del wizard (Voz).
 */

export const TONES = [
  { value: 'warm', label: 'Cálida' },
  { value: 'close', label: 'Cercana' },
  { value: 'aspirational', label: 'Aspiracional' },
  { value: 'professional', label: 'Profesional' },
  { value: 'playful', label: 'Divertida' },
];

export const FORMALITIES = [
  { value: 'informal', label: 'Informal' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'formal', label: 'Formal' },
];

const TONE_LABELS = Object.fromEntries(TONES.map((t) => [t.value, t.label]));


export function toneLabel(value) {
  return TONE_LABELS[value] || (value ? capitalize(value) : 'Sin definir');
}


function capitalize(s) {
  const str = String(s);
  return str.charAt(0).toUpperCase() + str.slice(1);
}


export function buildVoicePayload(form) {
  return {
    tone: form?.tone || 'warm',
    formality: form?.formality || 'neutral',
    energy_level: Math.min(10, Math.max(1, Number(form?.energy_level) || 5)),
    voice_id_ref: form?.voice_id_ref || null,
  };
}


/**
 * Hash determinista del estado del prompt para detectar cambios y
 * disparar re-generation de captions con debounce. No usa crypto —
 * solo necesita ser estable para los mismos inputs.
 */
export function captionPromptHash(form) {
  const payload = buildVoicePayload(form);
  return `${payload.tone}|${payload.formality}|${payload.energy_level}`;
}


export function validateMinimum(form) {
  if (!form?.tone) return { valid: false, error: 'Selecciona un tono de voz' };
  return { valid: true, error: null };
}
