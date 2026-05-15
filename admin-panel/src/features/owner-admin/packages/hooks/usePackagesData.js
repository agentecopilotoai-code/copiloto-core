import { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createTreatmentPackage,
  deactivateTreatmentPackage,
  listServices,
  listTreatmentPackages,
  updateTreatmentPackage,
} from '../../../../services/coreApi.js';
import { buildPayload, emptyForm, toForm } from '../packagesData.js';

/**
 * Data layer for the Negocio · Paquetes view. Owns the catalogue + service-
 * picker state, the modal/form state and the mutation handlers extracted from
 * the legacy `PackagesModule`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function usePackagesData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [packages, setPackages] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const [pkgs, svcs] = await Promise.all([
        listTreatmentPackages(session, tenantId, {}),
        listServices(session, tenantId, { includeInactive: false }),
      ]);
      setPackages(Array.isArray(pkgs) ? pkgs : []);
      setServices(Array.isArray(svcs) ? svcs : []);
    } catch (err) {
      setError(err?.message || 'No se pudieron cargar los paquetes.');
    } finally {
      setLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const serviceMap = useMemo(() => {
    const map = new Map();
    services.forEach((svc) => map.set(svc.id, svc));
    return map;
  }, [services]);

  const actions = {
    refresh,
    dismissError: () => setError(null),
    openCreate: () => {
      setForm(emptyForm());
      setError(null);
      setModalOpen(true);
    },
    openEdit: (pkg) => {
      setForm(toForm(pkg));
      setError(null);
      setModalOpen(true);
    },
    closeModal: () => setModalOpen(false),
    setFormField: (patch) => setForm((current) => ({ ...current, ...patch })),
    toggleService: (serviceId) =>
      setForm((current) => {
        const has = current.includes_service_ids.includes(serviceId);
        return {
          ...current,
          includes_service_ids: has
            ? current.includes_service_ids.filter((id) => id !== serviceId)
            : [...current.includes_service_ids, serviceId],
        };
      }),
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
          await updateTreatmentPackage(session, tenantId, form.id, payload);
        } else {
          await createTreatmentPackage(session, tenantId, payload);
        }
        setModalOpen(false);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo guardar el paquete.');
      } finally {
        setSaving(false);
      }
    },
    async deactivate(pkg) {
      if (!tenantId) return;
      const ok = await confirm({
        title: 'Desactivar paquete',
        body: `¿Desactivar el paquete "${pkg.name}"?`,
        danger: true,
      });
      if (!ok) return;
      setSaving(true);
      setError(null);
      try {
        await deactivateTreatmentPackage(session, tenantId, pkg.id);
        await refresh();
      } catch (err) {
        setError(err?.message || 'No se pudo desactivar el paquete.');
      } finally {
        setSaving(false);
      }
    },
  };

  return {
    state: { tenantId, packages, services, serviceMap, loading, saving, error, modalOpen, form },
    actions,
  };
}
