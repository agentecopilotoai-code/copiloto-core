/**
 * UI-INFLU-012 — Helpers puros para el paso 5 del wizard (Plataformas).
 */

export const PLATFORMS = [
  { value: 'instagram', label: 'Instagram', available: true },
  { value: 'tiktok', label: 'TikTok', available: false },
  { value: 'youtube', label: 'YouTube', available: false },
  { value: 'threads', label: 'Threads', available: false },
  { value: 'x', label: 'X', available: false },
  { value: 'facebook', label: 'Facebook', available: false },
];

export const MODES = [
  { value: 'auto_generate', label: 'Auto-generar contenido' },
  { value: 'manual_approval', label: 'Aprobación manual' },
  { value: 'hybrid', label: 'Híbrido' },
];

const CADENCE_PRESETS = {
  daily: 7,
  '5_week': 5,
  '3_week': 3,
  '1_week': 1,
};


export function cadenceToPerWeek(value) {
  if (typeof value === 'number') return value;
  const preset = CADENCE_PRESETS[value];
  if (preset !== undefined) return preset;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}


/**
 * Suma weekly credits = posts/semana * cost por kind.
 * `accounts`: lista de `{platform, posts_per_week, primary_kind}`.
 * `pricing`: map {kind: cost_credits} (TASK-INFLU-016).
 */
export function computeWeeklyCredits(accounts, pricing = { photo: 3, reel: 8 }) {
  if (!Array.isArray(accounts)) return 0;
  return accounts.reduce((acc, a) => {
    const perWeek = cadenceToPerWeek(a.posts_per_week);
    const cost = pricing[a.primary_kind || 'photo'] ?? 3;
    return acc + perWeek * cost;
  }, 0);
}


export function validateAtLeastOnePlatform(accounts) {
  return Array.isArray(accounts) && accounts.some((a) => a.handle);
}


export function modeLabel(value) {
  return MODES.find((m) => m.value === value)?.label ?? value;
}


/**
 * El flag `disclose_ai` no se puede desactivar desde el frontend (el
 * backend enforcer TASK-INFLU-018 también lo bloquea). Esta helper se
 * usa para deshabilitar el toggle en UI.
 */
export function cannotDisableDiscloseAi() {
  return true;
}
