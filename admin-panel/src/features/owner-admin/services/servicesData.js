/**
 * UI-007.4 — Negocio · Servicios: pure data helpers.
 *
 * Form shape, the applies_when rule normalisation (TASK-0054), payload building
 * (TASK-0052 recall config) and the WhatsApp preview — all extracted verbatim
 * from the legacy `ServiceCatalog` so they are shared by the split panels and
 * unit-testable without React.
 */

export const CURRENCIES = ['COP', 'USD', 'MXN', 'ARS', 'CLP', 'PEN', 'EUR'];

export const emptyForm = {
  name: '',
  category: '',
  description: '',
  price_amount: '',
  price_currency: 'COP',
  duration_minutes: 60,
  preparation_notes: '',
  post_service_notes: '',
  // TASK-0052: per-service recall configuration. Empty string means "no recall".
  recall_interval_days: '',
  recall_template_id: '',
  // TASK-0054: dynamic eligibility rule — list of {key, op, value} predicates
  // joined with AND. Empty list means "always applies".
  applies_when_rules: [],
  is_active: true,
};

export const APPLIES_WHEN_OPS = [
  { value: 'eq', label: 'es igual a' },
  { value: 'ne', label: 'es distinto de' },
  { value: 'in', label: 'está en lista' },
  { value: 'not_in', label: 'no está en lista' },
  { value: 'lt', label: 'es menor que' },
  { value: 'lte', label: 'es menor o igual que' },
  { value: 'gt', label: 'es mayor que' },
  { value: 'gte', label: 'es mayor o igual que' },
  { value: 'is_null', label: 'no fue respondida' },
  { value: 'is_not_null', label: 'fue respondida' },
  { value: 'contains_any', label: 'contiene alguno' },
  { value: 'contains_all', label: 'contiene todos' },
];

export const VALUELESS_OPS = new Set(['is_null', 'is_not_null']);
export const LIST_OPS = new Set(['in', 'not_in', 'contains_any', 'contains_all']);

export function parsePolicy(value) {
  if (!value) return {};
  if (typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch {
      return {};
    }
  }
  return value;
}

export function normalizeRuleValue(op, raw) {
  if (VALUELESS_OPS.has(op)) return undefined;
  if (LIST_OPS.has(op)) {
    if (Array.isArray(raw)) return raw.filter((item) => item !== '' && item !== null);
    if (typeof raw === 'string') {
      return raw
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
    }
    return [];
  }
  if (raw === '' || raw === null || raw === undefined) return '';
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (trimmed === '') return '';
    if (trimmed.toLowerCase() === 'true') return true;
    if (trimmed.toLowerCase() === 'false') return false;
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
    return trimmed;
  }
  return raw;
}

export function rulesToPayload(rules) {
  // Always wrap in all_of so the server normalizer accepts it. Empty list →
  // `{}` so the column defaults to "always applies".
  const cleaned = (rules || [])
    .map((rule) => {
      if (!rule || typeof rule.key !== 'string' || !rule.key.trim()) return null;
      const op = APPLIES_WHEN_OPS.some((entry) => entry.value === rule.op) ? rule.op : null;
      if (!op) return null;
      const node = { key: rule.key.trim(), op };
      const value = normalizeRuleValue(op, rule.value);
      if (value !== undefined) node.value = value;
      return node;
    })
    .filter(Boolean);
  if (!cleaned.length) return {};
  return { all_of: cleaned };
}

export function rulesFromService(service) {
  const stored = service?.applies_when;
  if (!stored || typeof stored !== 'object') return [];
  const list = Array.isArray(stored.all_of) ? stored.all_of : null;
  if (!list) return [];
  return list
    .filter((item) => item && typeof item.key === 'string' && typeof item.op === 'string')
    .map((item) => ({
      key: item.key,
      op: item.op,
      value:
        LIST_OPS.has(item.op) && Array.isArray(item.value)
          ? item.value.join(', ')
          : item.value !== undefined && item.value !== null
            ? String(item.value)
            : '',
    }));
}

export function formatPrice(amount, currency) {
  if (amount === null || amount === undefined || amount === '') return '—';
  const value = Number(amount);
  if (Number.isNaN(value)) return '—';
  try {
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: currency || 'COP',
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency || ''}`.trim();
  }
}

export function formatDuration(minutes) {
  if (!minutes) return '—';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins ? `${hours} h ${mins} min` : `${hours} h`;
}

export function buildPreview(form, tenant) {
  const name = (form.name || 'Servicio').trim();
  const price = form.price_amount ? formatPrice(form.price_amount, form.price_currency) : null;
  const duration = formatDuration(Number(form.duration_minutes) || 0);
  const lines = [
    `*${name}*${form.category ? ` — ${form.category}` : ''}`,
    form.description ? form.description : null,
    price ? `💰 ${price}` : null,
    `⏱ Duración aprox: ${duration}`,
    form.preparation_notes ? `📋 Antes de tu cita: ${form.preparation_notes}` : null,
  ].filter(Boolean);
  const header = tenant?.label ? `Catálogo de ${tenant.label.split(' · ')[0]}` : 'Catálogo';
  return `${header}\n\n${lines.join('\n')}`;
}

export function buildPayload(form) {
  // TASK-0052: empty string or 0 → null (no recall). Anything else parses to int.
  const recallRaw = form.recall_interval_days;
  let recallDays = null;
  if (recallRaw !== '' && recallRaw !== null && recallRaw !== undefined) {
    const parsed = Number(recallRaw);
    if (Number.isFinite(parsed) && parsed > 0) {
      recallDays = Math.trunc(parsed);
    }
  }
  return {
    name: form.name.trim(),
    category: form.category?.trim() || null,
    description: form.description?.trim() || null,
    price_amount:
      form.price_amount === '' || form.price_amount === null || form.price_amount === undefined
        ? null
        : Number(form.price_amount),
    price_currency: (form.price_currency || 'COP').toUpperCase(),
    duration_minutes: Number(form.duration_minutes) || 60,
    preparation_notes: form.preparation_notes?.trim() || null,
    post_service_notes: form.post_service_notes?.trim() || null,
    recall_interval_days: recallDays,
    recall_template_id: form.recall_template_id || null,
    // TASK-0054: emit the rule builder output as a normalized applies_when.
    applies_when: rulesToPayload(form.applies_when_rules || []),
    is_active: Boolean(form.is_active),
  };
}

/**
 * TASK-0052: preview of the date a recall would land if the same service were
 * completed today. Returns null when the interval is not a positive number.
 */
export function formatRecallPreview(intervalDays) {
  const parsed = Number(intervalDays);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const target = new Date(Date.now() + parsed * 24 * 60 * 60 * 1000);
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'long' }).format(target);
  } catch {
    return target.toISOString().slice(0, 10);
  }
}

/** Build the edit-form shape from a service record. */
export function formFromService(service) {
  return {
    name: service.name || '',
    category: service.category || '',
    description: service.description || '',
    price_amount: service.price_amount ?? '',
    price_currency: service.price_currency || 'COP',
    duration_minutes: service.duration_minutes || 60,
    preparation_notes: service.preparation_notes || '',
    post_service_notes: service.post_service_notes || '',
    recall_interval_days:
      service.recall_interval_days === null || service.recall_interval_days === undefined
        ? ''
        : String(service.recall_interval_days),
    recall_template_id: service.recall_template_id || '',
    applies_when_rules: rulesFromService(service),
    is_active: service.is_active !== false,
  };
}
