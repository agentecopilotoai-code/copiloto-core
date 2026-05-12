import { useEffect, useMemo, useState } from 'react';

import {
  cancelCampaign,
  createCampaign,
  launchCampaign,
  listCampaigns,
  listContactSegments,
  listContactTags,
  listWhatsappTemplates,
  previewCampaign,
  updateCampaign,
} from '../../../services/coreApi.js';

const STATUS_LABELS = {
  draft: 'Borrador',
  scheduled: 'Programada',
  running: 'En curso',
  completed: 'Completada',
  cancelled: 'Cancelada',
};

const EMPTY_FILTER = {
  tags: [],
  min_appointments: '',
  last_visit_before_days: '',
  last_visit_after_days: '',
  has_upcoming_appointment: '',
};

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return value;
  }
}

function parseVariables(text) {
  const result = {};
  text.split('\n').forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const idx = trimmed.indexOf('=');
    if (idx === -1) return;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (key) result[key] = value;
  });
  return result;
}

function serializeVariables(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return Object.entries(obj)
    .sort((a, b) => {
      const ai = Number.parseInt(a[0], 10);
      const bi = Number.parseInt(b[0], 10);
      if (Number.isFinite(ai) && Number.isFinite(bi)) return ai - bi;
      return a[0].localeCompare(b[0]);
    })
    .map(([k, v]) => `${k}=${v}`)
    .join('\n');
}

function buildSegmentPayload(form) {
  const segment = {};
  if (form.tags.length > 0) segment.tags = form.tags;
  if (form.min_appointments !== '' && form.min_appointments !== null)
    segment.min_appointments = Number.parseInt(form.min_appointments, 10);
  if (form.last_visit_before_days !== '' && form.last_visit_before_days !== null)
    segment.last_visit_before_days = Number.parseInt(form.last_visit_before_days, 10);
  if (form.last_visit_after_days !== '' && form.last_visit_after_days !== null)
    segment.last_visit_after_days = Number.parseInt(form.last_visit_after_days, 10);
  if (form.has_upcoming_appointment === 'yes') segment.has_upcoming_appointment = true;
  else if (form.has_upcoming_appointment === 'no') segment.has_upcoming_appointment = false;
  return segment;
}

function StatusPill({ status }) {
  const label = STATUS_LABELS[status] || status;
  return <span className={`status-pill status-${status}`}>{label}</span>;
}

function MetricBar({ label, value, total, color }) {
  const percent = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
        <span>{label}</span>
        <strong>{value} / {total}</strong>
      </div>
      <div
        style={{
          background: '#e2e8f0',
          borderRadius: '999px',
          height: '8px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            background: color,
            width: `${percent}%`,
            height: '100%',
            transition: 'width 200ms ease',
          }}
        />
      </div>
    </div>
  );
}

export function CampaignsModule({ module, session, tenant }) {
  const tenantId = tenant?.id;
  const [campaigns, setCampaigns] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);
  const [segments, setSegments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formMode, setFormMode] = useState('create');
  const [form, setForm] = useState({
    name: '',
    template_id: '',
    template_variables: '',
    scheduled_at: '',
    segment_id: '',
    segment: { ...EMPTY_FILTER },
  });

  const selectedCampaign = useMemo(
    () => campaigns.find((c) => c.id === selectedId) || null,
    [campaigns, selectedId],
  );

  function resetForm() {
    setForm({
      name: '',
      template_id: '',
      template_variables: '',
      scheduled_at: '',
      segment_id: '',
      segment: { ...EMPTY_FILTER },
    });
  }

  function refreshCampaigns() {
    if (!tenantId) return Promise.resolve();
    return listCampaigns(session, tenantId)
      .then((items) => {
        setCampaigns(items || []);
        if (items?.length && !items.some((c) => c.id === selectedId)) {
          setSelectedId(items[0].id);
        } else if (!items?.length) {
          setSelectedId(null);
        }
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshTemplates() {
    if (!tenantId) return Promise.resolve();
    return listWhatsappTemplates(session, tenantId, { status: 'approved' })
      .then((items) => setTemplates(items || []))
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshTags() {
    if (!tenantId) return Promise.resolve();
    return listContactTags(session, tenantId)
      .then((items) => setAvailableTags(items || []))
      .catch(() => setAvailableTags([]));
  }

  function refreshSegments() {
    if (!tenantId) return Promise.resolve();
    return listContactSegments(session, tenantId)
      .then((items) => setSegments(items || []))
      .catch(() => setSegments([]));
  }

  useEffect(() => {
    if (!tenantId) return;
    refreshCampaigns();
    refreshTemplates();
    refreshTags();
    refreshSegments();
  }, [tenantId]);

  function startCreate() {
    setFormMode('create');
    resetForm();
    setPreview(null);
    setShowForm(true);
  }

  function startEdit(campaign) {
    if (!campaign) return;
    setFormMode('edit');
    const segment = campaign.segment_filter || {};
    setForm({
      name: campaign.name || '',
      template_id: campaign.template_id || '',
      template_variables: serializeVariables(campaign.template_variables),
      scheduled_at: campaign.scheduled_at
        ? new Date(campaign.scheduled_at).toISOString().slice(0, 16)
        : '',
      segment_id: campaign.segment_id || '',
      segment: {
        tags: Array.isArray(segment.tags) ? segment.tags : [],
        min_appointments: segment.min_appointments ?? '',
        last_visit_before_days: segment.last_visit_before_days ?? '',
        last_visit_after_days: segment.last_visit_after_days ?? '',
        has_upcoming_appointment:
          segment.has_upcoming_appointment === true
            ? 'yes'
            : segment.has_upcoming_appointment === false
              ? 'no'
              : '',
      },
    });
    setPreview(null);
    setShowForm(true);
  }

  function buildPayload() {
    return {
      name: form.name.trim(),
      template_id: form.template_id || null,
      template_variables: parseVariables(form.template_variables),
      segment_filter: form.segment_id ? {} : buildSegmentPayload(form.segment),
      segment_id: form.segment_id || null,
      scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!form.name.trim() || !form.template_id) {
      setNotice({ type: 'error', text: 'Nombre y template aprobado son obligatorios.' });
      return;
    }
    setIsBusy(true);
    try {
      const payload = buildPayload();
      let saved;
      if (formMode === 'create') {
        saved = await createCampaign(session, tenantId, payload);
      } else {
        saved = await updateCampaign(session, tenantId, selectedId, payload);
      }
      setNotice({ type: 'success', text: 'Campaña guardada.' });
      await refreshCampaigns();
      setSelectedId(saved.id);
      setShowForm(false);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handlePreview() {
    if (!selectedId) return;
    setIsBusy(true);
    try {
      const data = await previewCampaign(session, tenantId, selectedId);
      setPreview(data);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleLaunch() {
    if (!selectedId) return;
    if (!window.confirm('¿Programar el envío de esta campaña? El worker procesará los destinatarios.')) {
      return;
    }
    setIsBusy(true);
    try {
      const next = selectedCampaign?.scheduled_at;
      await launchCampaign(session, tenantId, selectedId, next ? { scheduled_at: next } : {});
      setNotice({ type: 'success', text: 'Campaña programada. El worker la procesará.' });
      await refreshCampaigns();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCancel() {
    if (!selectedId) return;
    if (!window.confirm('¿Cancelar la campaña? Los destinatarios ya encolados aún se enviarán.')) return;
    setIsBusy(true);
    try {
      await cancelCampaign(session, tenantId, selectedId);
      setNotice({ type: 'success', text: 'Campaña cancelada.' });
      await refreshCampaigns();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function toggleTagInForm(tagId) {
    setForm((prev) => {
      const has = prev.segment.tags.includes(tagId);
      const next = has
        ? prev.segment.tags.filter((id) => id !== tagId)
        : [...prev.segment.tags, tagId];
      return { ...prev, segment: { ...prev.segment, tags: next } };
    });
  }

  if (!tenantId) {
    return (
      <section className="module-card">
        <div className="module-heading">
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <p className="hint">Selecciona un tenant para gestionar campañas.</p>
      </section>
    );
  }

  return (
    <section className="module-card campaigns-module">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Marketing conversacional</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="form-actions">
          <button className="primary-action" type="button" onClick={startCreate} disabled={isBusy}>
            Nueva campaña
          </button>
        </div>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      <div className="operations-layout" style={{ marginTop: '1rem' }}>
        <aside className="conversation-list" aria-label="Campañas">
          {campaigns.length === 0 ? (
            <p className="hint">No hay campañas todavía.</p>
          ) : null}
          {campaigns.map((campaign) => (
            <button
              type="button"
              key={campaign.id}
              className={`conversation-card ${campaign.id === selectedId ? 'active' : ''}`}
              onClick={() => {
                setSelectedId(campaign.id);
                setShowForm(false);
                setPreview(null);
              }}
            >
              <span>{campaign.name}</span>
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', alignItems: 'center' }}>
                <StatusPill status={campaign.status} />
                <small>{campaign.recipient_count || 0} destinatarios</small>
              </div>
              <small>
                {campaign.scheduled_at
                  ? `Enviar: ${formatDate(campaign.scheduled_at)}`
                  : 'Sin programar'}
              </small>
            </button>
          ))}
        </aside>

        <section className="conversation-detail">
          {showForm ? (
            <form className="form-grid" onSubmit={handleSubmit}>
              <label>
                Nombre
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Promo octubre clientes inactivos"
                />
              </label>
              <label>
                Template aprobado
                <select
                  required
                  value={form.template_id}
                  onChange={(e) => setForm((p) => ({ ...p, template_id: e.target.value }))}
                >
                  <option value="">— Selecciona un template —</option>
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {tpl.name} ({tpl.locale}) · {tpl.purpose}
                    </option>
                  ))}
                </select>
                {templates.length === 0 ? (
                  <small className="hint">
                    No hay templates aprobados. Crea uno en el módulo WhatsApp.
                  </small>
                ) : null}
              </label>
              <label>
                Variables (una por línea: <code>clave=valor</code>)
                <textarea
                  rows={4}
                  value={form.template_variables}
                  onChange={(e) => setForm((p) => ({ ...p, template_variables: e.target.value }))}
                  placeholder={'1=María\n2=20%'}
                />
              </label>
              <label>
                Fecha/hora de envío (opcional)
                <input
                  type="datetime-local"
                  value={form.scheduled_at}
                  onChange={(e) => setForm((p) => ({ ...p, scheduled_at: e.target.value }))}
                />
              </label>

              <label>
                Segmento guardado
                <select
                  value={form.segment_id}
                  onChange={(e) => setForm((p) => ({ ...p, segment_id: e.target.value }))}
                >
                  <option value="">— Sin segmento (usar filtros) —</option>
                  {segments.map((seg) => (
                    <option key={seg.id} value={seg.id}>
                      {seg.name} ({seg.contact_count})
                    </option>
                  ))}
                </select>
                {form.segment_id ? (
                  <small className="hint">
                    Al lanzar la campaña, el segmento se snapshotea y los destinatarios quedan fijos.
                  </small>
                ) : null}
              </label>

              <fieldset
                disabled={Boolean(form.segment_id)}
                style={{
                  gridColumn: '1 / -1',
                  border: '1px solid var(--border, #e2e8f0)',
                  borderRadius: 8,
                  padding: '0.8rem',
                  opacity: form.segment_id ? 0.5 : 1,
                }}
              >
                <legend>Filtros de segmento (alternativos)</legend>
                <div className="form-grid">
                  <label>
                    Mínimo de citas
                    <input
                      type="number"
                      min={0}
                      value={form.segment.min_appointments}
                      onChange={(e) =>
                        setForm((p) => ({ ...p, segment: { ...p.segment, min_appointments: e.target.value } }))
                      }
                    />
                  </label>
                  <label>
                    Última visita hace al menos (días)
                    <input
                      type="number"
                      min={0}
                      value={form.segment.last_visit_before_days}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          segment: { ...p.segment, last_visit_before_days: e.target.value },
                        }))
                      }
                    />
                  </label>
                  <label>
                    Última visita hace máximo (días)
                    <input
                      type="number"
                      min={0}
                      value={form.segment.last_visit_after_days}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          segment: { ...p.segment, last_visit_after_days: e.target.value },
                        }))
                      }
                    />
                  </label>
                  <label>
                    Cita futura agendada
                    <select
                      value={form.segment.has_upcoming_appointment}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          segment: { ...p.segment, has_upcoming_appointment: e.target.value },
                        }))
                      }
                    >
                      <option value="">Sin filtro</option>
                      <option value="yes">Sí, tiene cita futura</option>
                      <option value="no">No tiene cita futura</option>
                    </select>
                  </label>
                </div>
                <div style={{ marginTop: '0.6rem' }}>
                  <strong>Etiquetas</strong>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.4rem' }}>
                    {availableTags.length === 0 ? (
                      <small className="hint">No hay etiquetas configuradas.</small>
                    ) : null}
                    {availableTags.map((tag) => (
                      <button
                        type="button"
                        key={tag.id}
                        onClick={() => toggleTagInForm(tag.id)}
                        className="status-pill"
                        style={{
                          background: form.segment.tags.includes(tag.id) ? tag.color || '#4f6ef7' : '#e2e8f0',
                          color: form.segment.tags.includes(tag.id) ? '#fff' : '#1e293b',
                          border: 'none',
                          padding: '0.25rem 0.7rem',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                        }}
                      >
                        {tag.name}
                      </button>
                    ))}
                  </div>
                </div>
              </fieldset>

              <div className="form-actions" style={{ gridColumn: '1 / -1' }}>
                <button className="secondary-action" type="button" onClick={() => setShowForm(false)}>
                  Cancelar
                </button>
                <button className="primary-action" type="submit" disabled={isBusy}>
                  {formMode === 'create' ? 'Crear borrador' : 'Guardar cambios'}
                </button>
              </div>
            </form>
          ) : !selectedCampaign ? (
            <div className="empty-detail">
              <h3>Selecciona o crea una campaña</h3>
              <p className="hint">
                Las campañas envían un template aprobado a contactos que cumplen los criterios definidos. Solo
                se entrega a contactos con opt-in válido.
              </p>
            </div>
          ) : (
            <>
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Campaña</p>
                  <h3>{selectedCampaign.name}</h3>
                  <StatusPill status={selectedCampaign.status} />
                </div>
                <div className="form-actions">
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => startEdit(selectedCampaign)}
                    disabled={selectedCampaign.status !== 'draft' || isBusy}
                  >
                    Editar
                  </button>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={handlePreview}
                    disabled={isBusy}
                  >
                    Ver destinatarios estimados
                  </button>
                  {['draft', 'scheduled'].includes(selectedCampaign.status) ? (
                    <button
                      className="primary-action"
                      type="button"
                      onClick={handleLaunch}
                      disabled={isBusy}
                    >
                      {selectedCampaign.status === 'scheduled' ? 'Reprogramar' : 'Programar envío'}
                    </button>
                  ) : null}
                  {!['completed', 'cancelled'].includes(selectedCampaign.status) ? (
                    <button
                      className="danger-action"
                      type="button"
                      onClick={handleCancel}
                      disabled={isBusy}
                    >
                      Cancelar campaña
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="schedule-panel">
                <div>
                  <strong>Resumen</strong>
                  <ul className="hint" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                    <li>Template: <strong>{templates.find((t) => t.id === selectedCampaign.template_id)?.name || selectedCampaign.template_id || '—'}</strong></li>
                    <li>Destinatarios estimados: <strong>{selectedCampaign.recipient_count || 0}</strong></li>
                    <li>Envío programado: <strong>{formatDate(selectedCampaign.scheduled_at)}</strong></li>
                    <li>Inicio: <strong>{formatDate(selectedCampaign.started_at)}</strong></li>
                    <li>Fin: <strong>{formatDate(selectedCampaign.completed_at)}</strong></li>
                  </ul>
                </div>
              </div>

              <div className="schedule-panel">
                <div>
                  <strong>Métricas de entrega</strong>
                  <div style={{ marginTop: '0.6rem' }}>
                    <MetricBar
                      label="Enviados"
                      value={selectedCampaign.sent_count || 0}
                      total={selectedCampaign.recipient_count || 0}
                      color="#4f6ef7"
                    />
                    <MetricBar
                      label="Entregados"
                      value={selectedCampaign.delivered_count || 0}
                      total={selectedCampaign.recipient_count || 0}
                      color="#10b981"
                    />
                    <MetricBar
                      label="Leídos"
                      value={selectedCampaign.read_count || 0}
                      total={selectedCampaign.recipient_count || 0}
                      color="#0ea5e9"
                    />
                    <MetricBar
                      label="Fallidos"
                      value={selectedCampaign.failed_count || 0}
                      total={selectedCampaign.recipient_count || 0}
                      color="#ef4444"
                    />
                  </div>
                </div>
              </div>

              {preview ? (
                <div className="schedule-panel">
                  <div>
                    <strong>Destinatarios estimados: {preview.recipient_count}</strong>
                    {preview.sample?.length ? (
                      <ul style={{ listStyle: 'none', padding: 0, margin: '0.4rem 0 0' }}>
                        {preview.sample.map((contact) => (
                          <li key={contact.id} style={{ padding: '0.3rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                            <strong>{contact.display_name || contact.phone_e164}</strong>
                            <div className="hint" style={{ fontSize: '0.8rem' }}>
                              {contact.phone_e164} · opt-in: {contact.opt_in_status}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="hint">Ningún contacto coincide con los filtros.</p>
                    )}
                  </div>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </section>
  );
}
