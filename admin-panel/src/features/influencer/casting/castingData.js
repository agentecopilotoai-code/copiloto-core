/**
 * UI-INFLU-004 — Helpers puros para el Casting Home (sin estado React).
 *
 * Mantiene la lógica de formato + filtrado + sort fuera de los
 * componentes para que los tests unitarios sean rápidos y sin DOM.
 */

const CATEGORY_LABELS = {
  lifestyle: 'Lifestyle',
  fashion: 'Fashion',
  beauty: 'Beauty',
  editorial: 'Editorial',
  beach: 'Beach',
  travel: 'Travel',
};

export const CATEGORY_FILTER_OPTIONS = [
  { value: null, label: 'Todos' },
  { value: 'lifestyle', label: 'Lifestyle' },
  { value: 'fashion', label: 'Fashion' },
  { value: 'beauty', label: 'Beauty' },
  { value: 'editorial', label: 'Editorial' },
  { value: 'beach', label: 'Beach' },
  { value: 'travel', label: 'Travel' },
];

export const SORT_OPTIONS = [
  { value: 'activity', label: 'Ordenar: actividad' },
  { value: 'posts', label: 'Ordenar: posts' },
  { value: 'reach', label: 'Ordenar: alcance' },
];

export function categoryLabel(value) {
  if (!value) return 'Sin categoría';
  return CATEGORY_LABELS[String(value).toLowerCase()] || value;
}

/**
 * Formatea un número de alcance en formato humano: 12K / 3.4M / 250.
 */
export function formatReach(value) {
  const n = Number(value) || 0;
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${m % 1 === 0 ? m.toFixed(0) : m.toFixed(1)}M`;
  }
  if (n >= 1_000) {
    const k = n / 1_000;
    return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}K`;
  }
  return String(n);
}

/**
 * Engagement rate como porcentaje con 1 decimal (e.g. `5.7%`). Acepta
 * valores 0..1 (proporción) o 0..100 (ya pct). Si > 1 asume pct.
 */
export function formatEngagementRate(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0%';
  const pct = n > 1 ? n : n * 100;
  return `${pct.toFixed(1)}%`;
}

/**
 * Filtra personas por categoría. `null` o `undefined` devuelve todas.
 */
export function filterByCategory(personas, category) {
  if (!Array.isArray(personas)) return [];
  if (!category) return personas;
  const lower = String(category).toLowerCase();
  return personas.filter((p) => String(p.category || '').toLowerCase() === lower);
}

/**
 * Ordena personas por uno de los criterios soportados. Devuelve copia.
 *  - 'activity' → por engagement_rate desc.
 *  - 'posts'    → por posts_total desc.
 *  - 'reach'    → por reach_30d desc.
 *  Si el criterio no es conocido, se preserva el orden de entrada.
 */
export function sortPersonas(personas, criterion = 'activity') {
  if (!Array.isArray(personas)) return [];
  const copy = [...personas];
  if (criterion === 'posts') {
    copy.sort((a, b) => (b.posts_total ?? 0) - (a.posts_total ?? 0));
  } else if (criterion === 'reach') {
    copy.sort((a, b) => (b.reach_30d ?? 0) - (a.reach_30d ?? 0));
  } else if (criterion === 'activity') {
    copy.sort((a, b) => (b.engagement_rate ?? 0) - (a.engagement_rate ?? 0));
  }
  return copy;
}
