import { useEffect, useMemo, useState } from 'react';

import {
  createService,
  deactivateService,
  getTenantSettings,
  listPromotions,
  listServices,
  listWhatsappTemplates,
  reorderServices,
  updateService,
  updateTenantSettings,
} from '../../../services/coreApi.js';

function parsePolicy(value) {
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

const CURRENCIES = ['COP', 'USD', 'MXN', 'ARS', 'CLP', 'PEN', 'EUR'];

const emptyForm = {
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
  is_active: true,
};

function formatPrice(amount, currency) {
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

function formatDuration(minutes) {
  if (!minutes) return '—';
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function buildPreview(form, tenant) {
  const name = (form.name || 'Servicio').trim();
  const price = form.price_amount
    ? formatPrice(form.price_amount, form.price_currency)
    : null;
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

function buildPayload(form) {
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
    is_active: Boolean(form.is_active),
  };
}

// TASK-0052: preview of the date a recall would land if the same service were
// completed today. Useful so the operator picks an interval that makes sense
// (180 days for hygiene, 90 for dermatology controls, etc.).
function formatRecallPreview(intervalDays) {
  const parsed = Number(intervalDays);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const target = new Date(Date.now() + parsed * 24 * 60 * 60 * 1000);
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'long' }).format(target);
  } catch {
    return target.toISOString().slice(0, 10);
  }
}

export function ServiceCatalog({ module, session, tenant }) {
  const [services, setServices] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [defaultDuration, setDefaultDuration] = useState(60);
  const [tenantSettings, setTenantSettings] = useState(null);
  const [promotions, setPromotions] = useState([]);
  // TASK-0052: approved service_recall templates the operator can pick from.
  const [recallTemplates, setRecallTemplates] = useState([]);

  const tenantId = tenant?.id;
  const previewText = useMemo(() => buildPreview(form, tenant), [form, tenant]);

  function resetForm() {
    setForm(emptyForm);
    setEditingId(null);
  }

  async function loadServices() {
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
  }

  useEffect(() => {
    loadServices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, includeInactive]);

  useEffect(() => {
    if (!tenantId) return;
    getTenantSettings(session, tenantId)
      .then((settings) => {
        setTenantSettings(settings);
        const policy = parsePolicy(settings?.escalation_policy);
        const stored = policy?.service_durations?.default;
        if (typeof stored === 'number' && stored > 0) setDefaultDuration(stored);
      })
      .catch(() => {});
  }, [tenantId, session]);

  // TASK-0052: only approved templates are usable by the scheduler.
  useEffect(() => {
    if (!tenantId) return;
    listWhatsappTemplates(session, tenantId, { purpose: 'service_recall', status: 'approved' })
      .then((rows) => setRecallTemplates(Array.isArray(rows) ? rows : []))
      .catch(() => setRecallTemplates([]));
  }, [tenantId, session]);

  async function handleSaveDefaultDuration(event) {
    event.preventDefault();
    if (!tenantId || !tenantSettings) return;
    const minutes = Number(defaultDuration);
    if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 1440) {
      setNotice({ type: 'error', text: 'La duración por defecto debe ser un número entre 1 y 1440 minutos.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const policy = parsePolicy(tenantSettings.escalation_policy);
      const nextPolicy = {
        ...policy,
        service_durations: { ...(policy.service_durations || {}), default: minutes },
      };
      const updated = await updateTenantSettings(session, tenantId, {
        locale: tenantSettings.locale,
        business_hours: tenantSettings.business_hours,
        escalation_policy: nextPolicy,
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
  }

  async function handleSubmit(event) {
    event.preventDefault();
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
        await createService(session, tenantId, {
          ...payload,
          sort_order: services.length,
        });
        setNotice({ type: 'success', text: 'Servicio creado.' });
      }
      resetForm();
      await loadServices();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function startEdit(service) {
    setEditingId(service.id);
    setForm({
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
      is_active: service.is_active !== false,
    });
    setNotice(null);
  }

  async function handleDeactivate(service) {
    if (!tenantId) return;
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
  }

  async function moveService(index, direction) {
    if (!tenantId) return;
    const next = [...services];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved);
    const order = next.map((service, idx) => ({ id: service.id, sort_order: idx }));
    setServices(next);
    setIsBusy(true);
    try {
      await reorderServices(session, tenantId, order);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
      await loadServices();
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="module-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Catálogo</p>
          <h2>{module?.label || 'Servicios'}</h2>
          <p>{module?.summary || 'Configura los servicios que tu negocio ofrece a tus clientes.'}</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
        </div>
      </div>

      {!tenantId ? (
        <p className="hint">Selecciona un tenant para gestionar su catálogo de servicios.</p>
      ) : null}

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      {tenantId ? (
        <div className="wizard-panel">
          <form className="form-grid" onSubmit={handleSaveDefaultDuration} style={{ marginBottom: '0.75rem' }}>
            <label>
              Duración por defecto (minutos)
              <input
                disabled={!tenantSettings}
                min="1"
                max="1440"
                onChange={(event) => setDefaultDuration(event.target.value)}
                type="number"
                value={defaultDuration}
              />
            </label>
            <div className="form-actions">
              <button className="secondary-action" disabled={isBusy || !tenantSettings} type="submit">
                Guardar fallback
              </button>
              <p className="hint" style={{ marginLeft: '0.5rem' }}>
                Se usa cuando no hay catálogo o el servicio no tiene duración propia.
              </p>
            </div>
          </form>

          <div className="audit-actions" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
            <button className="primary-action" disabled={isLoading} onClick={loadServices} type="button">
              {isLoading ? 'Cargando…' : 'Refrescar listado'}
            </button>
            <label className="inline-check">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(event) => setIncludeInactive(event.target.checked)}
              />
              Mostrar inactivos
            </label>
          </div>

          {services.length === 0 ? (
            <p className="hint">Aún no hay servicios cargados. Crea el primero con el formulario.</p>
          ) : (
            <table className="audit-table" style={{ width: '100%', marginBottom: '1rem' }}>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nombre</th>
                  <th>Categoría</th>
                  <th>Precio</th>
                  <th>Duración</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {services.map((service, index) => {
                  const servicePromos = promotions.filter(
                    (p) =>
                      p.is_active
                      && (
                        !p.applies_to_service_ids
                        || p.applies_to_service_ids.length === 0
                        || p.applies_to_service_ids.includes(service.id)
                      ),
                  );
                  return (
                  <tr key={service.id} data-service-promos={servicePromos.length}>
                    <td>{index + 1}</td>
                    <td>
                      <strong>{service.name}</strong>
                      {service.description ? (
                        <div className="hint" style={{ marginTop: '0.25rem' }}>
                          {service.description}
                        </div>
                      ) : null}
                      {servicePromos.length ? (
                        <div style={{ marginTop: '0.3rem', display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                          {servicePromos.map((promo) => (
                            <span
                              key={promo.id}
                              className="status-pill"
                              style={{ background: '#0ea5e9', color: '#fff', fontSize: '0.7rem', padding: '0.05rem 0.4rem' }}
                              title="Promoción activa para este servicio"
                            >
                              🎁 {promo.name}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td>{service.category || '—'}</td>
                    <td>{formatPrice(service.price_amount, service.price_currency)}</td>
                    <td>{formatDuration(service.duration_minutes)}</td>
                    <td>
                      <span className={`status-badge ${service.is_active ? 'active' : 'suspended'}`}>
                        {service.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                        <button
                          className="secondary-action"
                          disabled={isBusy || index === 0}
                          onClick={() => moveService(index, -1)}
                          type="button"
                          aria-label="Subir orden"
                        >
                          ↑
                        </button>
                        <button
                          className="secondary-action"
                          disabled={isBusy || index === services.length - 1}
                          onClick={() => moveService(index, +1)}
                          type="button"
                          aria-label="Bajar orden"
                        >
                          ↓
                        </button>
                        <button
                          className="secondary-action"
                          disabled={isBusy}
                          onClick={() => startEdit(service)}
                          type="button"
                        >
                          Editar
                        </button>
                        {service.is_active ? (
                          <button
                            className="secondary-action"
                            disabled={isBusy}
                            onClick={() => handleDeactivate(service)}
                            type="button"
                          >
                            Desactivar
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <h3>{editingId ? 'Editar servicio' : 'Nuevo servicio'}</h3>
          <form className="form-grid" onSubmit={handleSubmit}>
            <label className="wide">
              Nombre
              <input
                maxLength={160}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
                value={form.name}
              />
            </label>
            <label>
              Categoría
              <input
                placeholder="Ej. Corte, Manicure, Consulta"
                maxLength={120}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
                value={form.category}
              />
            </label>
            <label>
              Estado
              <select
                value={form.is_active ? 'active' : 'inactive'}
                onChange={(event) => setForm({ ...form, is_active: event.target.value === 'active' })}
              >
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </label>
            <label>
              Precio
              <input
                min="0"
                step="0.01"
                type="number"
                value={form.price_amount}
                onChange={(event) => setForm({ ...form, price_amount: event.target.value })}
              />
            </label>
            <label>
              Moneda
              <select
                value={form.price_currency}
                onChange={(event) => setForm({ ...form, price_currency: event.target.value })}
              >
                {CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>{currency}</option>
                ))}
              </select>
            </label>
            <label>
              Duración (minutos)
              <input
                min="1"
                max="1440"
                required
                type="number"
                value={form.duration_minutes}
                onChange={(event) => setForm({ ...form, duration_minutes: event.target.value })}
              />
            </label>
            <label className="wide">
              Descripción
              <textarea
                maxLength={2000}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                rows={2}
                value={form.description}
              />
            </label>
            <label className="wide">
              Instrucciones de preparación (se envían al cliente antes del servicio)
              <textarea
                maxLength={2000}
                onChange={(event) => setForm({ ...form, preparation_notes: event.target.value })}
                rows={2}
                value={form.preparation_notes}
              />
            </label>
            <label className="wide">
              Instrucciones post-servicio (se envían al cliente después)
              <textarea
                maxLength={2000}
                onChange={(event) => setForm({ ...form, post_service_notes: event.target.value })}
                rows={2}
                value={form.post_service_notes}
              />
            </label>
            <label>
              Recordatorio de control cada N días
              <input
                min="0"
                max="3650"
                step="1"
                type="number"
                placeholder="Ej. 180 para control semestral"
                value={form.recall_interval_days}
                onChange={(event) => setForm({ ...form, recall_interval_days: event.target.value })}
              />
              <span className="hint" style={{ display: 'block', marginTop: '0.25rem' }}>
                Si lo dejas vacío, no se envía recordatorio.
                {(() => {
                  const preview = formatRecallPreview(form.recall_interval_days);
                  if (!preview) return null;
                  return ` Una cita completada hoy dispararía el recordatorio el ${preview}.`;
                })()}
              </span>
            </label>
            <label>
              Plantilla del recordatorio
              <select
                value={form.recall_template_id || ''}
                onChange={(event) => setForm({ ...form, recall_template_id: event.target.value })}
                disabled={!form.recall_interval_days}
              >
                <option value="">— Usar la plantilla aprobada por defecto —</option>
                {recallTemplates.map((tmpl) => (
                  <option key={tmpl.id} value={tmpl.id}>
                    {tmpl.name} ({tmpl.locale})
                  </option>
                ))}
              </select>
              {form.recall_interval_days && recallTemplates.length === 0 ? (
                <span className="hint" style={{ display: 'block', marginTop: '0.25rem', color: '#b91c1c' }}>
                  No hay plantillas service_recall aprobadas. Crea una en WhatsApp Templates antes de programar recordatorios.
                </span>
              ) : null}
            </label>
            <div className="builder-preview wide">
              <strong>Vista previa para WhatsApp</strong>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{previewText}</pre>
            </div>
            <div className="form-actions">
              <button className="primary-action" disabled={isBusy} type="submit">
                {editingId ? 'Actualizar servicio' : 'Crear servicio'}
              </button>
              {editingId ? (
                <button
                  className="secondary-action"
                  disabled={isBusy}
                  onClick={resetForm}
                  type="button"
                  style={{ marginLeft: '0.5rem' }}
                >
                  Cancelar edición
                </button>
              ) : null}
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}
