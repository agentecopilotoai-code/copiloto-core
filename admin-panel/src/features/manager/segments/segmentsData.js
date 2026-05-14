/**
 * UI-008.3 — Segmentos: pure data helpers.
 *
 * Segment-kind labels/tones, the rule-builder field/operator catalogues, the
 * empty segment-form shape, `formFromSegment`, `buildPayload` (with
 * validation), the rule-builder pure functions (add/update/remove rule,
 * default rule, `fieldKind`) and the rules ⇄ conditions converters — extracted
 * verbatim from the legacy `SegmentsModule` so the list / rule builder /
 * preview panel share them and they stay unit-testable without React.
 */

/** Spanish labels for each segment kind. */
export const KIND_LABELS = {
  dynamic: 'Dinámico (reglas)',
  static: 'Estático (snapshot)',
};

/** `StatusBadge` tone for each segment kind. */
export const KIND_TONES = {
  dynamic: 'accent',
  static: 'neutral',
};

/** The rule-builder field catalogue (value + label + kind). */
export const FIELD_OPTIONS = [
  { value: 'last_appointment_at', label: 'Última cita (fecha)', kind: 'date' },
  { value: 'total_appointments_completed', label: 'Citas completadas', kind: 'number' },
  { value: 'total_appointments_no_show', label: 'No-shows', kind: 'number' },
  { value: 'total_spent', label: 'Gasto total', kind: 'number' },
  { value: 'tags', label: 'Etiquetas', kind: 'array' },
  { value: 'lead_source.channel', label: 'Canal de origen', kind: 'text' },
  { value: 'created_at', label: 'Fecha de creación', kind: 'date' },
];

/** The rule-builder operator catalogue, keyed by field kind. */
export const OPERATORS_BY_KIND = {
  number: [
    { value: 'eq', label: '=' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '<=' },
    { value: 'gt', label: '>' },
    { value: 'gte', label: '>=' },
    { value: 'between', label: 'entre (a,b)' },
  ],
  date: [
    { value: 'lt_days_ago', label: 'hace más de N días' },
    { value: 'gte_days_ago', label: 'hace N días o menos' },
    { value: 'is_null', label: 'no tiene' },
    { value: 'is_not_null', label: 'tiene' },
  ],
  array: [
    { value: 'contains_any', label: 'contiene alguna' },
    { value: 'contains_all', label: 'contiene todas' },
    { value: 'is_empty', label: 'vacío' },
    { value: 'is_not_empty', label: 'no vacío' },
  ],
  text: [
    { value: 'eq', label: '=' },
    { value: 'in', label: 'en lista' },
    { value: 'is_null', label: 'no tiene' },
    { value: 'is_not_null', label: 'tiene' },
  ],
};

/** Operators that take no value input. */
export const VALUELESS_OPS = ['is_null', 'is_not_null', 'is_empty', 'is_not_empty'];

/** Operators whose value is a comma-separated list. */
export const LIST_OPS = ['contains_any', 'contains_all', 'in', 'between'];

/** The field kind for a rule field (defaults to `text`). */
export function fieldKind(field) {
  return FIELD_OPTIONS.find((f) => f.value === field)?.kind || 'text';
}

/** The operator catalogue for a given field kind. */
export function operatorsForField(field) {
  return OPERATORS_BY_KIND[fieldKind(field)] || OPERATORS_BY_KIND.text;
}

/** A blank rule row. */
export function defaultRule() {
  return { field: 'last_appointment_at', op: 'lt_days_ago', value: 60 };
}

/** Whether a rule's operator requires a value input. */
export function ruleNeedsValue(op) {
  return !VALUELESS_OPS.includes(op);
}

/** Update a rule's field — resets the operator to the new kind's first op. */
export function updateRuleField(rule, field) {
  const nextOp = (OPERATORS_BY_KIND[fieldKind(field)] || OPERATORS_BY_KIND.text)[0].value;
  return { ...rule, field, op: nextOp, value: '' };
}

/** Update a rule's operator (value untouched). */
export function updateRuleOp(rule, op) {
  return { ...rule, op };
}

/** Update a rule's value, casting numbers for numeric fields / `_days_ago` ops. */
export function updateRuleValue(rule, rawValue) {
  const numeric = fieldKind(rule.field) === 'number' || rule.op?.endsWith('_days_ago');
  return { ...rule, value: numeric ? Number(rawValue) : rawValue };
}

/** Parse a comma-separated value into an array (numbers for `between`). */
export function parseListValue(rule, rawValue) {
  const parts = String(rawValue)
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const cast = rule.op === 'between' ? parts.map(Number) : parts;
  return { ...rule, value: cast };
}

/** Add a default rule row to a rule array. */
export function addRule(items) {
  return [...items, defaultRule()];
}

/** Replace the rule at `index` in a rule array. */
export function replaceRule(items, index, next) {
  return items.map((rule, idx) => (idx === index ? next : rule));
}

/** Remove the rule at `index` from a rule array. */
export function removeRule(items, index) {
  return items.filter((_, idx) => idx !== index);
}

/** Split a segment's `rules` jsonb into `{ joiner, items }`. */
export function rulesToConditions(rules) {
  if (!rules || typeof rules !== 'object') return { joiner: 'all_of', items: [] };
  if (Array.isArray(rules.all_of)) return { joiner: 'all_of', items: rules.all_of };
  if (Array.isArray(rules.any_of)) return { joiner: 'any_of', items: rules.any_of };
  return { joiner: 'all_of', items: [] };
}

/** Build the `rules` jsonb from the joiner + the rule rows (drops empties). */
export function conditionsToRules(joiner, items) {
  const cleaned = items
    .filter((c) => c && c.field && c.op)
    .map((c) => {
      const out = { field: c.field, op: c.op };
      if (c.value !== undefined && c.value !== '' && c.value !== null) {
        out.value = c.value;
      }
      return out;
    });
  if (!cleaned.length) return {};
  return { [joiner]: cleaned };
}

/** Format an ISO date/time for the es-CO locale; `—` when empty. */
export function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

/** A blank segment form. */
export function emptySegmentForm() {
  return {
    name: '',
    description: '',
    kind: 'dynamic',
    joiner: 'all_of',
    items: [defaultRule()],
  };
}

/** Build the segment-form shape from a segment record. */
export function formFromSegment(segment) {
  const { joiner, items } = rulesToConditions(segment.rules || {});
  return {
    name: segment.name || '',
    description: segment.description || '',
    kind: segment.kind || 'dynamic',
    joiner,
    items: items.length ? items : [defaultRule()],
  };
}

/**
 * Build the create/update segment payload from the form. Returns
 * `{ error }` when the name is missing, otherwise `{ payload }`.
 */
export function buildPayload(form) {
  if (!form.name.trim()) {
    return { error: 'El nombre es obligatorio.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      kind: form.kind,
      rules: form.kind === 'dynamic' ? conditionsToRules(form.joiner, form.items) : {},
    },
  };
}
