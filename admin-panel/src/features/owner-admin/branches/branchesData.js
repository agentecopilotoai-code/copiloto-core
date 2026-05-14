/**
 * UI-007.7 — Negocio · Sedes: pure data helpers.
 *
 * Form shape, record↔form mapping, payload building, the Google Maps URL
 * builder (TASK-0058 mirror) and the opening-hours summary — extracted from the
 * legacy `BranchesModule` so they are shared by the list / drawer and
 * unit-testable without React.
 */

/** Weekday keys + short Spanish labels, in display order. */
export const WEEKDAYS = [
  { key: 'mon', label: 'Lun' },
  { key: 'tue', label: 'Mar' },
  { key: 'wed', label: 'Mié' },
  { key: 'thu', label: 'Jue' },
  { key: 'fri', label: 'Vie' },
  { key: 'sat', label: 'Sáb' },
  { key: 'sun', label: 'Dom' },
];

/** IANA timezones offered in the branch form. */
export const TIMEZONE_OPTIONS = [
  'America/Bogota',
  'America/Mexico_City',
  'America/Lima',
  'America/Santiago',
  'America/Argentina/Buenos_Aires',
  'America/Caracas',
  'America/Sao_Paulo',
  'Europe/Madrid',
];

/** Canonical Google Maps search URL prefix — mirrors `app/services/maps.py`. */
export const MAPS_BASE_URL = 'https://www.google.com/maps/search/?api=1&query=';

/** A blank branch form (the "Nueva sede" state). */
export function emptyForm() {
  return {
    id: null,
    name: '',
    code: '',
    address: '',
    city: '',
    state: '',
    country: 'CO',
    lat: '',
    lng: '',
    maps_url: '',
    phone_e164: '',
    timezone: 'America/Bogota',
    opening_hours: {},
    is_active: true,
    sort_order: 0,
  };
}

/** Build the edit-form shape from a branch record. */
export function toForm(branch) {
  return {
    id: branch.id,
    name: branch.name || '',
    code: branch.code || '',
    address: branch.address || '',
    city: branch.city || '',
    state: branch.state || '',
    country: branch.country || 'CO',
    lat: branch.lat ?? '',
    lng: branch.lng ?? '',
    maps_url: branch.maps_url || '',
    phone_e164: branch.phone_e164 || '',
    timezone: branch.timezone || 'America/Bogota',
    opening_hours: branch.opening_hours || {},
    is_active: branch.is_active !== false,
    sort_order: branch.sort_order || 0,
  };
}

/**
 * Build the API payload from the form. Returns `{ error }` when the form is
 * invalid (name + code required), otherwise `{ payload }`.
 */
export function buildPayload(form) {
  if (!form.name.trim()) {
    return { error: 'El nombre de la sede es obligatorio.' };
  }
  if (!form.code.trim()) {
    return { error: 'El código de la sede es obligatorio.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      code: form.code.trim(),
      address: form.address.trim() || null,
      city: form.city.trim() || null,
      state: form.state.trim() || null,
      country: form.country.trim().slice(0, 2).toUpperCase() || 'CO',
      lat: form.lat === '' ? null : Number(form.lat),
      lng: form.lng === '' ? null : Number(form.lng),
      maps_url: form.maps_url.trim() || null,
      phone_e164: form.phone_e164.trim() || null,
      timezone: form.timezone || 'America/Bogota',
      opening_hours: form.opening_hours || {},
      is_active: Boolean(form.is_active),
      sort_order: Number(form.sort_order) || 0,
    },
  };
}

/**
 * Mirror of `app/services/maps.py` `build_maps_url` so the admin sees the exact
 * URL the backend will persist when the field is left blank. Prefers valid
 * lat/lng over the free-text address.
 */
export function buildMapsUrlFromInputs(lat, lng, address) {
  const trimmedLat = (lat ?? '').toString().trim();
  const trimmedLng = (lng ?? '').toString().trim();
  if (trimmedLat !== '' && trimmedLng !== '') {
    const latNum = Number(trimmedLat);
    const lngNum = Number(trimmedLng);
    if (
      Number.isFinite(latNum) &&
      Number.isFinite(lngNum) &&
      latNum >= -90 &&
      latNum <= 90 &&
      lngNum >= -180 &&
      lngNum <= 180
    ) {
      return `${MAPS_BASE_URL}${encodeURIComponent(`${latNum},${lngNum}`)}`;
    }
  }
  const trimmedAddress = (address ?? '').trim();
  if (trimmedAddress) {
    return `${MAPS_BASE_URL}${encodeURIComponent(trimmedAddress)}`;
  }
  return null;
}

/** Format a branch's location line: address + city, or '—' when both empty. */
export function formatLocation(branch) {
  const parts = [branch.address, branch.city].map((p) => (p || '').trim()).filter(Boolean);
  return parts.length > 0 ? parts.join(', ') : '—';
}

function formatRanges(franjas) {
  return (franjas || [])
    .filter((f) => f && f.start && f.end)
    .map((f) => `${f.start}-${f.end}`)
    .join(', ');
}

/**
 * Compact human summary of an `opening_hours` map. Adjacent weekdays that share
 * the same ranges are grouped (e.g. "Lun-Vie 09:00-19:00 · Sáb 09:00-14:00").
 * Returns 'Sin horario configurado' when no day has ranges.
 */
export function summarizeHours(openingHours) {
  const groups = [];
  WEEKDAYS.forEach((day, index) => {
    const ranges = formatRanges((openingHours || {})[day.key]);
    if (!ranges) return;
    const last = groups[groups.length - 1];
    if (last && last.ranges === ranges && last.endIndex === index - 1) {
      last.endLabel = day.label;
      last.endIndex = index;
    } else {
      groups.push({ startLabel: day.label, endLabel: day.label, endIndex: index, ranges });
    }
  });
  if (groups.length === 0) return 'Sin horario configurado';
  return groups
    .map((g) => {
      const span = g.startLabel === g.endLabel ? g.startLabel : `${g.startLabel}-${g.endLabel}`;
      return `${span} ${g.ranges}`;
    })
    .join(' · ');
}
