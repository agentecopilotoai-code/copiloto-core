/**
 * UI-007.6 — Negocio · Suscripciones: pure data helpers.
 *
 * Plan form shape, record↔form mapping, payload building, the status / period
 * labels and the KPI derivation — extracted from the legacy
 * `SubscriptionsModule` so they are shared by the panels and unit-testable
 * without React.
 */

/** Billing-period options, mirrored from the backend enum (TASK-0075). */
export const BILLING_PERIODS = [
  { value: 'monthly', label: 'Mensual' },
  { value: 'quarterly', label: 'Trimestral' },
  { value: 'yearly', label: 'Anual' },
];

/** Subscriber tabs for the subscribers table. */
export const SUBSCRIBER_TABS = [
  { value: 'all', label: 'Todos' },
  { value: 'active', label: 'Activos' },
  { value: 'past_due', label: 'Past-due' },
  { value: 'cancelled', label: 'Cancelados' },
];

/** A blank plan form (the "Nuevo plan" state). */
export function emptyPlanForm() {
  return {
    id: null,
    name: '',
    description: '',
    billing_period: 'monthly',
    price_amount: 0,
    currency: 'COP',
    status: 'active',
  };
}

/** Build the edit-form shape from a subscription-plan record. */
export function toPlanForm(plan) {
  return {
    id: plan.id,
    name: plan.name || '',
    description: plan.description || '',
    billing_period: plan.billing_period || 'monthly',
    price_amount: plan.price_amount ?? 0,
    currency: plan.currency || 'COP',
    status: plan.status || 'active',
  };
}

/**
 * Build the API payload from the plan form. Returns `{ error }` when the form
 * is invalid (name required, price ≥ 0), otherwise `{ payload }`.
 */
export function buildPlanPayload(form) {
  if (!form.name.trim()) {
    return { error: 'El nombre del plan es obligatorio.' };
  }
  const amount = Number(form.price_amount);
  if (!Number.isFinite(amount) || amount < 0) {
    return { error: 'El precio debe ser un número mayor o igual a 0.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      description: form.description.trim() || null,
      billing_period: form.billing_period,
      price_amount: amount,
      currency: (form.currency || 'COP').toUpperCase().slice(0, 3),
      status: form.status,
    },
  };
}

/** Human label for a billing period. */
export function billingPeriodLabel(period) {
  const found = BILLING_PERIODS.find((p) => p.value === period);
  return found ? found.label : period || '';
}

/** Human label for a plan / subscription status. */
export function subscriptionStatusLabel(status) {
  switch (status) {
    case 'active':
      return 'Activo';
    case 'past_due':
      return 'Cobro fallido';
    case 'cancelled':
      return 'Cancelado';
    case 'archived':
      return 'Archivado';
    default:
      return status || '';
  }
}

/** `StatusBadge` tone for a subscription status. */
export function subscriptionStatusTone(status) {
  switch (status) {
    case 'active':
      return 'success';
    case 'past_due':
      return 'warning';
    default:
      return 'neutral';
  }
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

/** Short billing date (e.g. "21 may"), or '—' for nullish / invalid input. */
export function formatBillingDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' });
}

/** Normalise a plan's price to a monthly figure for MRR aggregation. */
export function monthlyAmount(plan) {
  const amount = Number(plan?.price_amount) || 0;
  switch (plan?.billing_period) {
    case 'yearly':
      return amount / 12;
    case 'quarterly':
      return amount / 3;
    default:
      return amount;
  }
}

/**
 * Derive the dashboard KPIs from the plan + subscriber lists. MRR is the sum of
 * each active subscriber's plan price normalised to a month — no SaaS-level
 * billing snapshot is modelled, so this is computed honestly from what the
 * `/subscription-plans` and `/subscriptions` endpoints already return.
 *
 * @param {Array<object>} plans
 * @param {Array<object>} subscribers
 */
export function computeKpis(plans, subscribers) {
  const byKey = new Map();
  plans.forEach((plan) => {
    byKey.set(plan.id, plan);
    if (plan.name) byKey.set(plan.name, plan);
  });

  const active = subscribers.filter((s) => s.status === 'active');
  const pastDue = subscribers.filter((s) => s.status === 'past_due');
  const cancelled = subscribers.filter((s) => s.status === 'cancelled');

  const mrr = active.reduce((sum, sub) => {
    const plan = byKey.get(sub.plan_id) || byKey.get(sub.plan_name);
    return sum + monthlyAmount(plan);
  }, 0);

  return {
    mrr,
    currency: plans[0]?.currency || 'COP',
    activeCount: active.length,
    pastDueCount: pastDue.length,
    cancelledCount: cancelled.length,
    activePlanCount: plans.filter((p) => p.status === 'active').length,
  };
}

/** Filter the subscriber list by the active subscriber tab. */
export function filterSubscribers(subscribers, tab) {
  if (tab === 'all') return subscribers;
  return subscribers.filter((s) => s.status === tab);
}
