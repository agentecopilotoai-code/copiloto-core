import { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createBranch,
  deactivateBranch,
  listBranches,
  updateBranch,
} from '../../../../services/coreApi.js';
import { buildMapsUrlFromInputs, buildPayload, emptyForm, toForm } from '../branchesData.js';

/**
 * Data layer for the Negocio · Sedes view. Owns the branch list, the
 * drawer/form state (including the per-day opening-hours editing helpers) and
 * the mutation handlers extracted verbatim from the legacy `BranchesModule`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useBranchesData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listBranches(session, tenantId, {});
      setBranches(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err?.message || 'No se pudieron cargar las sedes.');
    } finally {
      setLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const mapsPreviewUrl = useMemo(
    () => buildMapsUrlFromInputs(form.lat, form.lng, form.address),
    [form.lat, form.lng, form.address],
  );

  function setHoursForDay(dayKey, franjas) {
    setForm((current) => ({
      ...current,
      opening_hours: { ...(current.opening_hours || {}), [dayKey]: franjas },
    }));
  }

  const actions = {
    refresh,
    dismissError: () => setError(null),
    openCreate: () => {
      setForm(emptyForm());
      setError(null);
      setDrawerOpen(true);
    },
    openEdit: (branch) => {
      setForm(toForm(branch));
      setError(null);
      setDrawerOpen(true);
    },
    closeDrawer: () => setDrawerOpen(false),
    setFormField: (patch) => setForm((current) => ({ ...current, ...patch })),
    generateMapsUrl: () => {
      setForm((current) => {
        const generated = buildMapsUrlFromInputs(current.lat, current.lng, current.address);
        return generated ? { ...current, maps_url: generated } : current;
      });
    },
    addFranja: (dayKey) => {
      const current = (form.opening_hours || {})[dayKey] || [];
      setHoursForDay(dayKey, [...current, { start: '09:00', end: '18:00' }]);
    },
    removeFranja: (dayKey, index) => {
      const current = (form.opening_hours || {})[dayKey] || [];
      setHoursForDay(
        dayKey,
        current.filter((_, i) => i !== index),
      );
    },
    updateFranja: (dayKey, index, field, value) => {
      const current = (form.opening_hours || {})[dayKey] || [];
      setHoursForDay(
        dayKey,
        current.map((franja, i) => (i === index ? { ...franja, [field]: value } : franja)),
      );
    },
    async save() {
      if (!tenantId) return;
      const { payload, error: validationError } = buildPayload(form);
      if (validationError) {
        setError(validationError);
        return;
      }
      setSaving(true);
      setError(null);
      try {
        if (form.id) {
          await updateBranch(session, tenantId, form.id, payload);
        } else {
          await createBranch(session, tenantId, payload);
        }
        setDrawerOpen(false);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo guardar la sede.');
      } finally {
        setSaving(false);
      }
    },
    async deactivate(branch) {
      if (!tenantId) return;
      const ok = await confirm({
        title: 'Desactivar sede',
        body: `¿Desactivar la sede "${branch.name}"?`,
        danger: true,
      });
      if (!ok) return;
      setSaving(true);
      setError(null);
      try {
        await deactivateBranch(session, tenantId, branch.id);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo desactivar la sede.');
      } finally {
        setSaving(false);
      }
    },
  };

  return {
    state: { tenantId, branches, loading, saving, error, drawerOpen, form, mapsPreviewUrl },
    actions,
  };
}
