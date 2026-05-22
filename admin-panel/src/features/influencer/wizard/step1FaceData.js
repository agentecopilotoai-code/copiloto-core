/**
 * UI-INFLU-008 — Helpers puros para el paso 1 del wizard (Cara).
 *
 * **Mapping UI → backend**: el diseñador (`docs/influencer/03a_*`) muestra
 * controles ricos (color de ojos con paleta de colores, color/largo/estilo
 * de pelo, slider de tono de piel, etc.) pero el backend `FaceStep`
 * (`wizard_models.py`) acepta enums acotados:
 *
 *   - `eye_color: Literal['brown', 'black', 'blue', 'green', 'hazel', 'gray', 'amber']`
 *   - `hair_color: Literal['black', 'brown', 'blonde', 'red', 'gray', 'white', 'colored']`
 *   - `hair_style: Literal['short', 'medium', 'long', 'curly', 'wavy', 'straight', 'shaved']`
 *   - `skin_tone: Literal['light', 'medium-light', 'medium', 'medium-dark', 'dark']`
 *   - `age_range: Literal['18-24', '25-34', '35-44', '45-54', '55+']`
 *   - `ethnicity: str` (libre, max 64 chars)
 *
 * Mantenemos el state UI rico (forma de ojos, estilo de pelo Suelto/Bob/Coleta,
 * subtono Frío/Neutro/Cálido) en sessionStorage del wizard para preservar
 * preferencias del user entre sesiones, pero NO los enviamos al backend.
 * `buildFacePayload()` filtra a los campos que el backend conoce.
 */

// ─── Listas UI ricas (con labels en español + valor backend mapeado) ─────

export const ETHNICITIES = [
  { value: 'europea', label: 'Europea' },
  { value: 'latina', label: 'Latina' },
  { value: 'asiática', label: 'Asiática' },
  { value: 'africana', label: 'Africana' },
  { value: 'oriente medio', label: 'Middle East.' },
  { value: 'mixta', label: 'Mixta' },
];

export const EYE_COLORS = [
  { value: 'brown', label: 'Marrón', hex: '#5b3a1e' },
  { value: 'hazel', label: 'Avellana', hex: '#a06e3c' },
  { value: 'green', label: 'Verde', hex: '#8da26b' },
  { value: 'blue', label: 'Azul', hex: '#6ea2c6' },
  { value: 'gray', label: 'Gris', hex: '#9aa3a8' },
  { value: 'amber', label: 'Ámbar', hex: '#c89058' },
];

// Forma de ojos — UI only, no se envía al backend (no está en el schema).
export const EYE_SHAPES = [
  { value: 'almond', label: 'Almendrados' },
  { value: 'round', label: 'Redondos' },
  { value: 'droopy', label: 'Caídos' },
  { value: 'monolid', label: 'Monolid' },
];

export const HAIR_COLORS = [
  { value: 'black', label: 'Negro', hex: '#2a2520' },
  // Castaño y Caoba caen en `brown` del backend; el UI los distingue.
  { value: 'brown', label: 'Castaño', hex: '#6b3f2a' },
  { value: 'brown_caoba', label: 'Caoba', hex: '#7a3e2a', backend: 'brown' },
  { value: 'blonde', label: 'Rubio', hex: '#caa66a' },
  // Platino → backend acepta `blonde` (no hay 'platinum'). UI lo trata
  // como variante visual.
  { value: 'platinum', label: 'Platino', hex: '#dccca4', backend: 'blonde' },
  { value: 'red', label: 'Pelirrojo', hex: '#a04930' },
];

// Estilo de pelo — UI only (los valores no matchean el enum del backend
// que es semántico, no de forma). El backend recibe `hair_style` derivado
// del slider de largo via `hairLengthToStyle`.
export const HAIR_STYLES = [
  { value: 'loose', label: 'Suelto' },
  { value: 'updo', label: 'Recogido' },
  { value: 'ponytail', label: 'Coleta' },
  { value: 'braid', label: 'Trenza' },
  { value: 'bob', label: 'Bob' },
  { value: 'wavy', label: 'Ondas' },
];

// Subtono de piel — UI only (3 chips); el backend recibe `skin_tone`
// (5 buckets) derivado del slider de tono.
export const SKIN_SUBTONES = [
  { value: 'cool', label: 'Frío' },
  { value: 'neutral', label: 'Neutro' },
  { value: 'warm', label: 'Cálido' },
];

// ─── Mappers UI → backend enums ──────────────────────────────────────────

/**
 * Slider de largo de pelo (0-100 cm) → `hair_style` del backend.
 * Buckets: corto (<30), medio (<60), largo (>=60).
 */
export function hairLengthToStyle(cm) {
  const n = Number(cm) || 0;
  if (n < 30) return 'short';
  if (n < 60) return 'medium';
  return 'long';
}

/**
 * Slider de tono de piel (0-100) → `skin_tone` del backend.
 * Buckets equidistantes sobre 5 valores.
 */
export function skinSliderToTone(value) {
  const n = Number(value) || 0;
  if (n < 20) return 'light';
  if (n < 40) return 'medium-light';
  if (n < 60) return 'medium';
  if (n < 80) return 'medium-dark';
  return 'dark';
}

/**
 * Slider de edad (18-60+ años) → `age_range` del backend.
 */
export function ageToRange(years) {
  const n = Number(years) || 25;
  if (n < 25) return '18-24';
  if (n < 35) return '25-34';
  if (n < 45) return '35-44';
  if (n < 55) return '45-54';
  return '55+';
}

/**
 * Devuelve el valor `hair_color` del backend dado el `hair_color` del UI
 * (que puede ser `brown_caoba`/`platinum` etc — variantes visuales que
 * caen en el mismo bucket backend).
 */
export function hairColorToBackend(uiValue) {
  const entry = HAIR_COLORS.find((c) => c.value === uiValue);
  return entry?.backend || entry?.value || uiValue;
}

// ─── Legacy FACE_OPTIONS (mantenido por backward-compat con tests) ───────

export const FACE_OPTIONS = {
  ethnicity: ETHNICITIES.map((e) => e.value),
  eye_color: EYE_COLORS.map((c) => c.value),
  hair_color: HAIR_COLORS.map((c) => c.backend || c.value).filter(
    (v, i, arr) => arr.indexOf(v) === i,
  ),
  hair_style: ['short', 'medium', 'long', 'curly', 'wavy', 'straight', 'shaved'],
  skin_tone: ['light', 'medium-light', 'medium', 'medium-dark', 'dark'],
  age_range: ['18-24', '25-34', '35-44', '45-54', '55+'],
};


export function defaultsForRandom() {
  // Valores ricos del UI + los derivados que el backend exige.
  return {
    starting_point: 'random',
    ethnicity: 'latina',
    age_years: 27,
    age_range: '25-34',
    eye_color: 'brown',
    eye_shape: 'almond',
    hair_color: 'brown',
    hair_length_cm: 50,
    hair_style: 'medium',
    hair_style_ui: 'loose',
    skin_slider: 50,
    skin_tone: 'medium',
    skin_subtone: 'neutral',
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
 * del formulario. Aplica los mappers UI→backend:
 *
 *   - `hair_length_cm` → `hair_style` ('short'/'medium'/'long').
 *   - `skin_slider` → `skin_tone` ('light'/'medium-light'/...).
 *   - `age_years` → `age_range` ('18-24'/...).
 *   - `hair_color` → bucket backend (UI 'caoba'/'platinum' → 'brown'/'blonde').
 *
 * Los campos UI-only (`eye_shape`, `hair_style_ui`, `skin_subtone`,
 * `age_years`, `skin_slider`, `hair_length_cm`) se OMITEN del payload —
 * el backend rechazaría enums fuera de su Literal.
 */
export function buildFacePayload(form) {
  if (!form) return {};
  const payload = {};

  if (form.starting_point) payload.starting_point = form.starting_point;
  if (form.ethnicity) payload.ethnicity = form.ethnicity;
  if (form.eye_color) payload.eye_color = form.eye_color;

  // hair_color: mapear caoba/platino al bucket backend.
  if (form.hair_color) payload.hair_color = hairColorToBackend(form.hair_color);

  // hair_style: derivar del slider de largo si está, sino fallback al
  // valor directo (caso defaultsForRandom que setea hair_style explícito).
  if (form.hair_length_cm != null) {
    payload.hair_style = hairLengthToStyle(form.hair_length_cm);
  } else if (form.hair_style) {
    payload.hair_style = form.hair_style;
  }

  // skin_tone: derivar del slider si está.
  if (form.skin_slider != null) {
    payload.skin_tone = skinSliderToTone(form.skin_slider);
  } else if (form.skin_tone) {
    payload.skin_tone = form.skin_tone;
  }

  // age_range: derivar de years si está.
  if (form.age_years != null) {
    payload.age_range = ageToRange(form.age_years);
  } else if (form.age_range) {
    payload.age_range = form.age_range;
  }

  if (form.variations) payload.variations = form.variations;
  return payload;
}


/**
 * Marca una variación como canonical y devuelve la lista actualizada.
 */
export function canonicalFromVariations(variations, canonicalId) {
  if (!Array.isArray(variations)) return [];
  return variations.map((v) => ({ ...v, canonical: v.id === canonicalId }));
}
