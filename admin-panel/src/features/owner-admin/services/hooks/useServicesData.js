import { useCallback, useEffect, useState } from 'react';

import {
  createService,
  deactivateService,
  getTenantSettings,
  listPromotions,
  listQualificationQuestions,
  listServices,
  listWhatsappTemplates,
  reorderServices,
  updateService,
  updateTenantSettings,
} from '../../../../services/coreApi.js';
import { buildPayload, emptyForm, formFromService, parsePolicy } from '../servicesData.js';

const PRESET_KEYS = [
  { key: 'budget_tier', label: 'Presupuesto (tier_value numérico)' },
  { key: 'urgency_level', label: 'Urgencia (emergency/high/normal/low)' },
];

/**
 * Data layer for the Negocio · Servicios view. Owns the catalogue state and the
 * mutation handlers extracted verbatim from the legacy `ServiceCatalog`; the
 * split panels stay presentational and consume `state` / `actions`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useServicesData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [services, setServices] = useState([]);
  const [promotions, setPromotions] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [defaultDuration, setDefaultDuration] = useState(60);
  const [tenantSettings, setTenantSettings] = useState(null);
  const [recallTemplates, setRecallTemplates] = useState([]);
  const [qualificationKeys, setQualificationKeys] = useState([]);

  const loadServices = useCallback(async () => {
    if (!tenantId) return;
    setIsLoading(true);
    setNotice(null);
    try {
      const [serviceResult, promoResult] = await Promise.all([
        listServices(session, tenantId, { includeInactive }),
        listPromotions(session, tenantId, { includeInactive: false }).catch(() => []),
      ]);
      setServices(Array.isArray(serviceResult) ? serviceResult : []);
      setPromotions(Array.isArray(promoResult) ? promoResult : []);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsLoading(false);
    }
  }, [session, tenantId, includeInactive]);

  useEffect(() => {
    loadServices();
  }, [loadServices]);

  useEffect(() => {
    if (!tenantId) return;
    getTenantSettings(session, tenantId)
      .then((settings) => {
        setTenantSettings(settings);
        const stored = parsePolicy(settings?.escalation_policy)?.service_durations?.default;
        if (typeof stored === 'number' && stored > 0) setDefaultDuration(stored);
      })
      .catch(() => {});
  }, [tenantId, session]);

  useEffect(() => {
    if (!tenantId) return;
    listWhatsappTemplates(session, tenantId, { purpose: 'service_recall', status: 'approved' })
      .then((rows) => setRecallTemplates(Array.isArray(rows) ? rows : []))
      .catch(() => setRecallTemplates([]));
  }, [tenantId, session]);

  useEffect(() => {
    if (!tenantId) {
      setQualificationKeys([]);
      return;
    }
    listQualificationQuestions(session, tenantId)
      .then((rows) => {
        const fromQuestions = (Array.isArray(rows) ? rows : [])
          .filter((q) => typeof q.key === 'string' && q.key)
          .map((q) => ({ key: q.key, label: `${q.label} (${q.kind})` }));
        const merged = [...PRESET_KEYS];
        fromQuestions.forEach((entry) => {
          if (!merged.some((m) => m.key === entry.key)) merged.push(entry);
        });
        setQualificationKeys(merged);
      })
      .catch(() => setQualificationKeys([...PRESET_KEYS]));
  }, [tenantId, session]);

  function resetForm() {
    setForm(emptyForm);
    setEditingId(null);
  }

  const actions = {
    setForm,
    setIncludeInactive,
    setDefaultDuration,
    refresh: loadServices,
    resetForm,
    dismissNotice: () => setNotice(null),
    startEdit: (service) => {
      setEditingId(service.id);
      setForm(formFromService(service));
      setNotice(null);
    },
    addRule: (qualificationKey) =>
      setForm((current) => ({
        ...current,
        applies_when_rules: [
          ...(current.applies_when_rules || []),
          { key: qualificationKey || '', op: 'eq', value: '' },
        ],
      })),
    updateRule: (index, patch) =>
      setForm((current) => {
        const next = [...(current.applies_when_rules || [])];
        next[index] = { ...next[index], ...patch };
        return { ...current, applies_when_rules: next };
      }),
    removeRule: (index) =>
      setForm((current) => {
        const next = [...(current.applies_when_rules || [])];
        next.splice(index, 1);
        return { ...current, applies_when_rules: next };
      }),
    async saveDefaultDuration() {
      if (!tenantId || !tenantSettings) return;
      const minutes = Number(defaultDuration);
      if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 1440) {
        setNotice({
          type: 'error',
          text: 'La duración por defecto debe ser un número entre 1 y 1440 minutos.',
        });
        return;
      }
      setIsBusy(true);
      setNotice(null);
      try {
        const policy = parsePolicy(tenantSettings.escalation_policy);
        const updated = await updateTenantSettings(session, tenantId, {
          locale: tenantSettings.locale,
          business_hours: tenantSettings.business_hours,
          escalation_policy: {
            ...policy,
            service_durations: { ...(policy.service_durations || {}), default: minutes },
          },
          pii_policy: tenantSettings.pii_policy,
          no_train: tenantSettings.no_train,
        });
        setTenantSettings(updated);
        setNotice({ type: 'success', text: 'Duración por defecto guardada.' });
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async submit() {
      if (!tenantId) return;
      if (!form.name.trim()) {
        setNotice({ type: 'error', text: 'El nombre del servicio es obligatorio.' });
        return;
      }
      const payload = buildPayload(form);
      setIsBusy(true);
      setNotice(null);
      try {
        if (editingId) {
          await updateService(session, tenantId, editingId, payload);
          setNotice({ type: 'success', text: 'Servicio actualizado.' });
        } else {
          await createService(session, tenantId, { ...payload, sort_order: services.length });
          setNotice({ type: 'success', text: 'Servicio creado.' });
        }
        resetForm();
        await loadServices();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async deactivate(service) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      if (!window.confirm(`¿Desactivar el servicio "${service.name}"?`)) return;
      setIsBusy(true);
      setNotice(null);
      try {
        await deactivateService(session, tenantId, service.id);
        setNotice({ type: 'success', text: 'Servicio desactivado.' });
        if (editingId === service.id) resetForm();
        await loadServices();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async move(index, direction) {
      if (!tenantId) return;
      const next = [...services];
      const target = index + direction;
      if (target < 0 || target >= next.length) return;
      const [moved] = next.splice(index, 1);
      next.splice(target, 0, moved);
      setServices(next);
      setIsBusy(true);
      try {
        await reorderServices(
          session,
          tenantId,
          next.map((service, idx) => ({ id: service.id, sort_order: idx })),
        );
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
        await loadServices();
      } finally {
        setIsBusy(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      services,
      promotions,
      form,
      editingId,
      isLoading,
      isBusy,
      notice,
      includeInactive,
      defaultDuration,
      tenantSettings,
      recallTemplates,
      qualificationKeys,
    },
    actions,
  };
}
