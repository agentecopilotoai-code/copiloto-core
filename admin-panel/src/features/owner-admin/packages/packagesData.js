/**
 * UI-007.5 — Negocio · Paquetes: pure data helpers.
 *
 * Form shape, record↔form mapping, payload building and the included-services
 * label — extracted from the legacy `PackagesModule` so they are shared by the
 * table / modal and unit-testable without React.
 */

/** A blank package form (the "Nuevo paquete" state). */
export function emptyForm() {
  return {
    id: null,
    name: '',
    description: '',
    total_sessions: 5,
    validity_days: '',
    price_amount: 0,
    price_currency: 'COP',
    includes_service_ids: [],
    is_active: true,
    sort_order: 0,
  };
}

/** Build the edit-form shape from a treatment-package record. */
export function toForm(pkg) {
  return {
    id: pkg.id,
    name: pkg.name || '',
    description: pkg.description || '',
    total_sessions: pkg.total_sessions ?? 1,
    validity_days: pkg.validity_days ?? '',
    price_amount: pkg.price_amount ?? 0,
    price_currency: pkg.price_currency || 'COP',
    includes_service_ids: Array.isArray(pkg.includes_service_ids)
      ? pkg.includes_service_ids
      : [],
    is_active: pkg.is_active !== false,
    sort_order: pkg.sort_order || 0,
  };
}

/**
 * Build the API payload from the form. Returns `{ error }` when the form is
 * invalid (name required, total_sessions > 0), otherwise `{ payload }`.
 */
export function buildPayload(form) {
  if (!form.name.trim()) {
    return { error: 'El nombre es obligatorio.' };
  }
  const total = Number(form.total_sessions);
  if (!Number.isFinite(total) || total <= 0) {
    return { error: 'El total de sesiones debe ser mayor a 0.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      description: form.description.trim() || null,
      total_sessions: total,
      validity_days: form.validity_days === '' ? null : Number(form.validity_days),
      price_amount: Number(form.price_amount) || 0,
      price_currency: (form.price_currency || 'COP').toUpperCase().slice(0, 3),
      includes_service_ids: form.includes_service_ids,
      is_active: Boolean(form.is_active),
      sort_order: Number(form.sort_order) || 0,
    },
  };
}

/**
 * Human label for a package's included services. An empty list means the
 * package applies to any service.
 *
 * @param {Array<string>} ids
 * @param {Map<string, object>} serviceMap service id → service record
 */
export function describeServices(ids, serviceMap) {
  if (!ids || ids.length === 0) return 'Aplica a cualquier servicio';
  return ids.map((id) => serviceMap.get(id)?.name || String(id).slice(0, 8)).join(', ');
}

/** Format a price amount + ISO currency, or '—' for nullish input. */
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
    return `${value.toFixed(0)} ${currency || ''}`.trim();
  }
}
