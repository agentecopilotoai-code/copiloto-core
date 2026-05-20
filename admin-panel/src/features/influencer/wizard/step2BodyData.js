/**
 * UI-INFLU-009 — Helpers puros para el paso 2 del wizard (Cuerpo).
 */

export const SILHOUETTES = [
  { value: 'slim', label: 'Slim' },
  { value: 'athletic', label: 'Athletic' },
  { value: 'curvy', label: 'Curvy' },
  { value: 'average', label: 'Average' },
];

export const POSTURES = [
  { value: 'confident', label: 'Segura' },
  { value: 'casual', label: 'Casual' },
  { value: 'elegant', label: 'Elegante' },
  { value: 'sporty', label: 'Deportiva' },
];

export const HEIGHT_MIN_CM = 140;
export const HEIGHT_MAX_CM = 210;

const SILHOUETTE_LABELS = Object.fromEntries(
  SILHOUETTES.map((s) => [s.value, s.label.toUpperCase()]),
);

export function silhouetteLabel(value) {
  return SILHOUETTE_LABELS[value] || (value ? value.toUpperCase() : 'SIN DEFINIR');
}

export function validateHeight(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return { valid: false, error: 'Altura debe ser un número' };
  if (n < HEIGHT_MIN_CM || n > HEIGHT_MAX_CM) {
    return { valid: false, error: `Altura debe estar entre ${HEIGHT_MIN_CM} y ${HEIGHT_MAX_CM} cm` };
  }
  return { valid: true, error: null };
}

export function buildBodyPayload(form) {
  return {
    silhouette: form?.silhouette ?? 'average',
    height_cm: Number(form?.height_cm) || 170,
    posture: form?.posture ?? 'confident',
  };
}
