/**
 * UI-INFLU-013 — Helpers puros para el composer "Generar contenido".
 */

export const KINDS = [
  { value: 'photo', label: 'Foto', cost: 3, badge: null },
  { value: 'reel', label: 'Reel', cost: 8, badge: 'HOT' },
  { value: 'carousel', label: 'Carrusel', cost: 10, badge: null },
  { value: 'story', label: 'Historia', cost: 2, badge: null },
  { value: 'ad', label: 'Anuncio', cost: 5, badge: null },
];

const KIND_FORMATS = {
  photo: ['1:1', '4:5', '9:16', '16:9'],
  reel: ['9:16'],
  carousel: ['1:1', '4:5'],
  story: ['9:16'],
  ad: ['1:1', '4:5', '9:16', '16:9'],
};

export const PROMPT_MAX = 1000;


export function kindMeta(value) {
  return KINDS.find((k) => k.value === value) || null;
}


export function validateFormatForKind(kind, format) {
  const allowed = KIND_FORMATS[kind] || [];
  return allowed.includes(format);
}


export function formatsForKind(kind) {
  return KIND_FORMATS[kind] || [];
}


export function computeCost(kind, count) {
  const meta = kindMeta(kind);
  if (!meta) return 0;
  return meta.cost * Math.max(1, Number(count) || 1);
}


export function promptWithinLimit(prompt) {
  return String(prompt || '').length <= PROMPT_MAX;
}


export function costExceedsBalance(kind, count, balance) {
  return computeCost(kind, count) > Number(balance ?? 0);
}


export function buildGeneratePayload(form) {
  const kind = form?.kind || 'photo';
  const format = validateFormatForKind(kind, form?.format)
    ? form.format
    : (formatsForKind(kind)[0] || '1:1');
  return {
    kind,
    prompt: String(form?.prompt || '').slice(0, PROMPT_MAX),
    format,
    count: Math.min(10, Math.max(1, Number(form?.count) || 1)),
    params: {
      style: form?.style || null,
      location: form?.location || null,
      reference_image_url: form?.reference_image_url || null,
      safety_mode: form?.safety_mode !== false,
    },
  };
}
