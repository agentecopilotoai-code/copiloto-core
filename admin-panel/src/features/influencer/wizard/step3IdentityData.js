/**
 * UI-INFLU-010 — Helpers puros para el paso 3 del wizard (Identidad).
 */

const HANDLE_RE = /^[a-z0-9][a-z0-9_]{2,29}$/;
export const DESCRIPTION_MAX = 280;

export const CATEGORIES = [
  'Lifestyle', 'Fashion', 'Beauty', 'Editorial', 'Beach', 'Travel',
];


export function validateHandle(value) {
  const v = String(value || '').trim().toLowerCase();
  if (!v) return { valid: false, error: 'Handle requerido' };
  if (!HANDLE_RE.test(v)) return { valid: false, error: 'Handle: a-z, 0-9, _; 3-30 chars; debe empezar con letra/número' };
  return { valid: true, error: null, normalized: v };
}


export function descriptionWithinLimit(value) {
  return (String(value || '').length) <= DESCRIPTION_MAX;
}


export function buildIdentityPayload(form) {
  const handleResult = validateHandle(form?.handle);
  return {
    name: String(form?.name || '').trim(),
    handle: handleResult.normalized || '',
    age: Number(form?.age) || 18,
    city: String(form?.city || '').trim(),
    country: String(form?.country || '').trim(),
    languages: Array.isArray(form?.languages) ? form.languages.slice(0, 8) : [],
    brands: Array.isArray(form?.brands) ? form.brands.slice(0, 20) : [],
    categories: Array.isArray(form?.categories) ? form.categories.slice(0, 10) : [],
    description: String(form?.description || '').slice(0, DESCRIPTION_MAX),
    latitude: form?.latitude == null ? null : Number(form.latitude),
    longitude: form?.longitude == null ? null : Number(form.longitude),
  };
}


export function previewCardData(form) {
  const payload = buildIdentityPayload(form);
  return {
    handle: payload.handle ? `@${payload.handle}` : '',
    location: [payload.city, payload.country].filter(Boolean).join(', '),
    description: payload.description,
  };
}


/**
 * Debounce simple sin librerías (lo usa el Step3Identity para chequeo
 * de handle único). 300ms es un buen balance.
 */
export function debounceHandleCheck(fn, ms = 300) {
  let timer = null;
  return (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
