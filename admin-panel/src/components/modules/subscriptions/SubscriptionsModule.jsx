import { useEffect, useMemo, useState } from 'react';

import {
  archiveSubscriptionPlan,
  cancelContactSubscription,
  createSubscriptionPlan,
  listContactSubscriptions,
  listSubscriptionPlans,
  updateSubscriptionPlan,
} from '../../../services/coreApi.js';

const BILLING_PERIODS = [
  { value: 'monthly', label: 'Mensual' },
  { value: 'quarterly', label: 'Trimestral' },
  { value: 'yearly', label: 'Anual' },
];

function emptyPlanForm() {
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

function toPlanForm(plan) {
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

function statusLabel(status) {
  if (status === 'active') return 'Activo';
  if (status === 'past_due') return 'Cobro fallido';
  if (status === 'cancelled') return 'Cancelado';
  if (status === 'archived') return 'Archivado';
  return status || '';
}

export function SubscriptionsModule({ module, session, tenant }) {
  const [plans, setPlans] = useState([]);
  const [subscribers, setSubscribers] = useState([]);
  const [form, setForm] = useState(emptyPlanForm);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function refresh() {
    if (!tenant?.id) return;
    setLoading(true);
    setError(null);
    try {
      const [planRows, subRows] = await Promise.all([
        listSubscriptionPlans(session, tenant.id, {}),
        listContactSubscriptions(session, tenant.id, {}),
      ]);
      setPlans(Array.isArray(planRows) ? planRows : []);
      setSubscribers(Array.isArray(subRows) ? subRows : []);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar las suscripciones.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  function resetForm() {
    setForm(emptyPlanForm());
  }

  function selectForEdit(plan) {
    setForm(toPlanForm(plan));
  }

  async function handleSave(evt) {
    evt.preventDefault();
    if (!tenant?.id) return;
    if (!form.name.trim()) {
      setError('El nombre del plan es obligatorio.');
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      billing_period: form.billing_period,
      price_amount: Number(form.price_amount) || 0,
      currency: (form.currency || 'COP').toUpperCase().slice(0, 3),
      status: form.status,
    };
    try {
      if (form.id) {
        await updateSubscriptionPlan(session, tenant.id, form.id, payload);
      } else {
        await createSubscriptionPlan(session, tenant.id, payload);
      }
      resetForm();
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo guardar el plan.');
    } finally {
      setSaving(false);
    }
  }

  async function handleArchive(plan) {
    if (!tenant?.id) return;
    if (!window.confirm(`¿Archivar el plan "${plan.name}"?`)) return;
    setSaving(true);
    setError(null);
    try {
      await archiveSubscriptionPlan(session, tenant.id, plan.id);
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo archivar el plan.');
    } finally {
      setSaving(false);
    }
  }

  async function handleCancelSubscription(sub) {
    if (!tenant?.id) return;
    if (!window.confirm(`¿Cancelar la suscripción de ${sub.contact_display_name || 'este contacto'}?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await cancelContactSubscription(session, tenant.id, sub.id);
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo cancelar la suscripción.');
    } finally {
      setSaving(false);
    }
  }

  const activePlans = useMemo(() => plans.filter((p) => p.status === 'active'), [plans]);
  const archivedPlans = useMemo(() => plans.filter((p) => p.status !== 'active'), [plans]);
  const activeSubscribers = subscribers.filter((s) => s.status === 'active');
  const pastDueSubscribers = subscribers.filter((s) => s.status === 'past_due');
  const cancelledSubscribers = subscribers.filter((s) => s.status === 'cancelled');

  return (
    <section className="module-card subscriptions-module" data-module-key="subscriptions">
      <header>
        <h2>{module?.label || 'Suscripciones'}</h2>
        <p className="hint">{module?.summary}</p>
      </header>

      {error ? (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      ) : null}

      <form className="subscriptions-form" onSubmit={handleSave} aria-label="Formulario de plan de suscripción">
        <div className="grid-2">
          <label>
            Nombre del plan
            <input
              required
              maxLength={200}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Ej: Membresía mensual gimnasio"
            />
          </label>
          <label>
            Descripción
            <input
              maxLength={2000}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
        </div>
        <div className="grid-3">
          <label>
            Frecuencia
            <select
              value={form.billing_period}
              onChange={(e) => setForm({ ...form, billing_period: e.target.value })}
            >
              {BILLING_PERIODS.map((bp) => (
                <option key={bp.value} value={bp.value}>
                  {bp.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Precio
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.price_amount}
              onChange={(e) => setForm({ ...form, price_amount: e.target.value })}
            />
          </label>
          <label>
            Moneda
            <input
              maxLength={3}
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
          </label>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.status === 'active'}
            onChange={(e) => setForm({ ...form, status: e.target.checked ? 'active' : 'archived' })}
          />
          Plan activo
        </label>
        <div className="actions">
          <button type="submit" disabled={saving}>
            {form.id ? 'Guardar cambios' : 'Crear plan'}
          </button>
          {form.id ? (
            <button type="button" onClick={resetForm} disabled={saving}>
              Cancelar
            </button>
          ) : null}
        </div>
      </form>

      <h3>Planes activos ({activePlans.length})</h3>
      {loading ? <p>Cargando…</p> : null}
      <ul className="subscriptions-plan-list">
        {activePlans.map((plan) => (
          <li className="subscriptions-plan-row" key={plan.id}>
            <div>
              <strong>{plan.name}</strong>{' '}
              <span className="hint">
                {plan.price_amount} {plan.currency} / {statusLabel(plan.billing_period) || plan.billing_period}
              </span>
              {plan.description ? <div className="hint">{plan.description}</div> : null}
            </div>
            <div className="actions">
              <button type="button" onClick={() => selectForEdit(plan)}>
                Editar
              </button>
              <button type="button" onClick={() => handleArchive(plan)}>
                Archivar
              </button>
            </div>
          </li>
        ))}
      </ul>

      {archivedPlans.length > 0 ? (
        <>
          <h3>Planes archivados ({archivedPlans.length})</h3>
          <ul className="subscriptions-plan-list inactive">
            {archivedPlans.map((plan) => (
              <li className="subscriptions-plan-row" key={plan.id}>
                <div>
                  <strong>{plan.name}</strong>{' '}
                  <span className="hint">
                    {plan.price_amount} {plan.currency} / {plan.billing_period}
                  </span>
                </div>
                <div className="actions">
                  <button type="button" onClick={() => selectForEdit(plan)}>
                    Reactivar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h3>Suscriptores activos ({activeSubscribers.length})</h3>
      <table className="subscriptions-subscribers-table">
        <thead>
          <tr>
            <th>Contacto</th>
            <th>Plan</th>
            <th>Próximo cobro</th>
            <th>Estado</th>
            <th aria-label="acciones" />
          </tr>
        </thead>
        <tbody>
          {activeSubscribers.map((sub) => (
            <tr key={sub.id}>
              <td>{sub.contact_display_name || sub.contact_phone_e164 || sub.contact_id}</td>
              <td>{sub.plan_name}</td>
              <td>{sub.next_billing_at ? new Date(sub.next_billing_at).toLocaleString() : '—'}</td>
              <td>{statusLabel(sub.status)}</td>
              <td>
                <button type="button" onClick={() => handleCancelSubscription(sub)}>
                  Cancelar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {pastDueSubscribers.length > 0 ? (
        <>
          <h3>Con cobro fallido ({pastDueSubscribers.length})</h3>
          <table className="subscriptions-subscribers-table past-due">
            <thead>
              <tr>
                <th>Contacto</th>
                <th>Plan</th>
                <th>Último intento</th>
                <th>Link reintento</th>
              </tr>
            </thead>
            <tbody>
              {pastDueSubscribers.map((sub) => (
                <tr key={sub.id}>
                  <td>{sub.contact_display_name || sub.contact_phone_e164 || sub.contact_id}</td>
                  <td>{sub.plan_name}</td>
                  <td>{sub.last_invoice_at ? new Date(sub.last_invoice_at).toLocaleString() : '—'}</td>
                  <td>
                    {sub.retry_payment_link ? (
                      <a href={sub.retry_payment_link} target="_blank" rel="noreferrer">
                        Abrir
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {cancelledSubscribers.length > 0 ? (
        <>
          <h3>Cancelados ({cancelledSubscribers.length})</h3>
          <p className="hint">
            Los suscriptores cancelados ya no reciben cobros. Quedan en el historial para auditoría.
          </p>
        </>
      ) : null}
    </section>
  );
}
