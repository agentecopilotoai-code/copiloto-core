import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  archiveSubscriptionPlan,
  cancelContactSubscription,
  createSubscriptionPlan,
  listContactSubscriptions,
  listSubscriptionPlans,
  updateSubscriptionPlan,
} from '../../../../services/coreApi.js';
import {
  buildPlanPayload,
  computeKpis,
  emptyPlanForm,
  filterSubscribers,
  toPlanForm,
} from '../subscriptionsData.js';

/**
 * Data layer for the Negocio · Suscripciones view. Owns the plans + subscribers
 * state, the modal/form state, the subscriber tab and the mutation handlers
 * extracted verbatim from the legacy `SubscriptionsModule`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useSubscriptionsData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [plans, setPlans] = useState([]);
  const [subscribers, setSubscribers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(emptyPlanForm);
  const [subscriberTab, setSubscriberTab] = useState('all');

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const [planRows, subRows] = await Promise.all([
        listSubscriptionPlans(session, tenantId, {}),
        listContactSubscriptions(session, tenantId, {}),
      ]);
      setPlans(Array.isArray(planRows) ? planRows : []);
      setSubscribers(Array.isArray(subRows) ? subRows : []);
    } catch (err) {
      setError(err?.message || 'No se pudieron cargar las suscripciones.');
    } finally {
      setLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const kpis = useMemo(() => computeKpis(plans, subscribers), [plans, subscribers]);
  const visibleSubscribers = useMemo(
    () => filterSubscribers(subscribers, subscriberTab),
    [subscribers, subscriberTab],
  );

  const actions = {
    refresh,
    dismissError: () => setError(null),
    setSubscriberTab,
    openCreate: () => {
      setForm(emptyPlanForm());
      setError(null);
      setModalOpen(true);
    },
    openEdit: (plan) => {
      setForm(toPlanForm(plan));
      setError(null);
      setModalOpen(true);
    },
    closeModal: () => setModalOpen(false),
    setFormField: (patch) => setForm((current) => ({ ...current, ...patch })),
    async save() {
      if (!tenantId) return;
      const { payload, error: validationError } = buildPlanPayload(form);
      if (validationError) {
        setError(validationError);
        return;
      }
      setSaving(true);
      setError(null);
      try {
        if (form.id) {
          await updateSubscriptionPlan(session, tenantId, form.id, payload);
        } else {
          await createSubscriptionPlan(session, tenantId, payload);
        }
        setModalOpen(false);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo guardar el plan.');
      } finally {
        setSaving(false);
      }
    },
    async archivePlan(plan) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      if (!window.confirm(`¿Archivar el plan "${plan.name}"?`)) return;
      setSaving(true);
      setError(null);
      try {
        await archiveSubscriptionPlan(session, tenantId, plan.id);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo archivar el plan.');
      } finally {
        setSaving(false);
      }
    },
    async cancelSubscription(sub) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      const who = sub.contact_display_name || sub.contact_phone_e164 || 'este contacto';
      if (!window.confirm(`¿Cancelar la suscripción de ${who}?`)) return;
      setSaving(true);
      setError(null);
      try {
        await cancelContactSubscription(session, tenantId, sub.id);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo cancelar la suscripción.');
      } finally {
        setSaving(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      plans,
      subscribers,
      visibleSubscribers,
      kpis,
      loading,
      saving,
      error,
      modalOpen,
      form,
      subscriberTab,
    },
    actions,
  };
}
