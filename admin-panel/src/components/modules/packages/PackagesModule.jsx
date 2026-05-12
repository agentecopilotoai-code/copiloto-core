import { useEffect, useMemo, useState } from 'react';

import {
  createTreatmentPackage,
  deactivateTreatmentPackage,
  listServices,
  listTreatmentPackages,
  updateTreatmentPackage,
} from '../../../services/coreApi.js';

function emptyForm() {
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

function toForm(pkg) {
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

export function PackagesModule({ module, session, tenant }) {
  const [packages, setPackages] = useState([]);
  const [services, setServices] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function refresh() {
    if (!tenant?.id) return;
    setLoading(true);
    setError(null);
    try {
      const [pkgs, svcs] = await Promise.all([
        listTreatmentPackages(session, tenant.id, {}),
        listServices(session, tenant.id, { includeInactive: false }),
      ]);
      setPackages(Array.isArray(pkgs) ? pkgs : []);
      setServices(Array.isArray(svcs) ? svcs : []);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar los paquetes.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  const serviceMap = useMemo(() => {
    const map = new Map();
    services.forEach((svc) => map.set(svc.id, svc));
    return map;
  }, [services]);

  function resetForm() {
    setForm(emptyForm());
  }

  function selectForEdit(pkg) {
    setForm(toForm(pkg));
  }

  function toggleService(serviceId) {
    setForm((prev) => {
      const has = prev.includes_service_ids.includes(serviceId);
      return {
        ...prev,
        includes_service_ids: has
          ? prev.includes_service_ids.filter((id) => id !== serviceId)
          : [...prev.includes_service_ids, serviceId],
      };
    });
  }

  async function handleSave(evt) {
    evt.preventDefault();
    if (!tenant?.id) return;
    if (!form.name.trim()) {
      setError('El nombre es obligatorio.');
      return;
    }
    const total = Number(form.total_sessions);
    if (!Number.isFinite(total) || total <= 0) {
      setError('El total de sesiones debe ser mayor a 0.');
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      total_sessions: total,
      validity_days: form.validity_days === '' ? null : Number(form.validity_days),
      price_amount: Number(form.price_amount) || 0,
      price_currency: (form.price_currency || 'COP').toUpperCase().slice(0, 3),
      includes_service_ids: form.includes_service_ids,
      is_active: !!form.is_active,
      sort_order: Number(form.sort_order) || 0,
    };
    try {
      if (form.id) {
        await updateTreatmentPackage(session, tenant.id, form.id, payload);
      } else {
        await createTreatmentPackage(session, tenant.id, payload);
      }
      resetForm();
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo guardar el paquete.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(pkg) {
    if (!tenant?.id) return;
    if (!window.confirm(`¿Desactivar el paquete "${pkg.name}"?`)) return;
    setSaving(true);
    setError(null);
    try {
      await deactivateTreatmentPackage(session, tenant.id, pkg.id);
      await refresh();
    } catch (err) {
      setError(err.message || 'No se pudo desactivar el paquete.');
    } finally {
      setSaving(false);
    }
  }

  const activePackages = packages.filter((p) => p.is_active);
  const inactivePackages = packages.filter((p) => !p.is_active);

  function describeServices(ids) {
    if (!ids || ids.length === 0) return 'Aplica a cualquier servicio';
    return ids
      .map((id) => serviceMap.get(id)?.name || id.slice(0, 8))
      .join(', ');
  }

  return (
    <section className="module-card packages-module" data-module-key="packages">
      <header>
        <h2>{module?.label || 'Paquetes'}</h2>
        <p className="hint">{module?.summary}</p>
      </header>

      {error ? (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      ) : null}

      <form className="packages-form" onSubmit={handleSave} aria-label="Formulario de paquete">
        <div className="grid-2">
          <label>
            Nombre
            <input
              required
              maxLength={200}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Ej: 5 sesiones de fisioterapia"
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
            Total de sesiones
            <input
              required
              type="number"
              min="1"
              max="500"
              value={form.total_sessions}
              onChange={(e) => setForm({ ...form, total_sessions: e.target.value })}
            />
          </label>
          <label>
            Vencimiento (días)
            <input
              type="number"
              min="1"
              max="3650"
              value={form.validity_days}
              onChange={(e) => setForm({ ...form, validity_days: e.target.value })}
              placeholder="Sin vencimiento"
            />
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
        </div>
        <div className="grid-2">
          <label>
            Moneda
            <input
              maxLength={3}
              value={form.price_currency}
              onChange={(e) => setForm({ ...form, price_currency: e.target.value })}
            />
          </label>
          <label>
            Orden
            <input
              type="number"
              min="0"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
            />
          </label>
        </div>

        <fieldset className="packages-services">
          <legend>Servicios incluidos (vacío = todos)</legend>
          {services.length === 0 ? (
            <p className="hint">No hay servicios activos.</p>
          ) : (
            <ul className="packages-services-list">
              {services.map((svc) => (
                <li key={svc.id}>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={form.includes_service_ids.includes(svc.id)}
                      onChange={() => toggleService(svc.id)}
                    />
                    {svc.name}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
          />
          Activo
        </label>

        <div className="actions">
          <button type="submit" disabled={saving}>
            {form.id ? 'Guardar cambios' : 'Crear paquete'}
          </button>
          {form.id ? (
            <button type="button" onClick={resetForm} disabled={saving}>
              Cancelar
            </button>
          ) : null}
        </div>
      </form>

      <h3>Paquetes activos ({activePackages.length})</h3>
      {loading ? <p>Cargando…</p> : null}
      <ul className="packages-list">
        {activePackages.map((pkg) => (
          <li className="packages-row" key={pkg.id}>
            <div>
              <strong>{pkg.name}</strong>{' '}
              <span className="hint">
                {pkg.total_sessions} sesiones · {pkg.price_amount} {pkg.price_currency}
                {pkg.validity_days ? ` · vence en ${pkg.validity_days}d` : ''}
              </span>
              <div className="hint">{describeServices(pkg.includes_service_ids)}</div>
              {pkg.description ? <div className="hint">{pkg.description}</div> : null}
            </div>
            <div className="actions">
              <button type="button" onClick={() => selectForEdit(pkg)}>
                Editar
              </button>
              <button type="button" onClick={() => handleDeactivate(pkg)}>
                Desactivar
              </button>
            </div>
          </li>
        ))}
      </ul>

      {inactivePackages.length > 0 ? (
        <>
          <h3>Inactivos ({inactivePackages.length})</h3>
          <ul className="packages-list inactive">
            {inactivePackages.map((pkg) => (
              <li className="packages-row" key={pkg.id}>
                <div>
                  <strong>{pkg.name}</strong>{' '}
                  <span className="hint">
                    {pkg.total_sessions} sesiones · {pkg.price_amount} {pkg.price_currency}
                  </span>
                </div>
                <div className="actions">
                  <button type="button" onClick={() => selectForEdit(pkg)}>
                    Reactivar (editar)
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
