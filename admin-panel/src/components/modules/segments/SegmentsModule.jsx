import { useEffect, useMemo, useState } from 'react';

import {
  createContactSegment,
  deleteContactSegment,
  listContactSegments,
  previewContactSegment,
  refreshContactSegment,
  updateContactSegment,
} from '../../../services/coreApi.js';

const KIND_LABELS = {
  dynamic: 'Dinámico (reglas)',
  static: 'Estático (snapshot)',
};

const FIELD_OPTIONS = [
  { value: 'last_appointment_at', label: 'Última cita (fecha)', kind: 'date' },
  { value: 'total_appointments_completed', label: 'Citas completadas', kind: 'number' },
  { value: 'total_appointments_no_show', label: 'No-shows', kind: 'number' },
  { value: 'total_spent', label: 'Gasto total', kind: 'number' },
  { value: 'tags', label: 'Etiquetas', kind: 'array' },
  { value: 'lead_source.channel', label: 'Canal de origen', kind: 'text' },
  { value: 'created_at', label: 'Fecha de creación', kind: 'date' },
];

const OPERATORS_BY_KIND = {
  number: [
    { value: 'eq', label: '=' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '<=' },
    { value: 'gt', label: '>' },
    { value: 'gte', label: '>=' },
    { value: 'between', label: 'entre (a,b)' },
  ],
  date: [
    { value: 'lt_days_ago', label: 'hace más de N días' },
    { value: 'gte_days_ago', label: 'hace N días o menos' },
    { value: 'is_null', label: 'no tiene' },
    { value: 'is_not_null', label: 'tiene' },
  ],
  array: [
    { value: 'contains_any', label: 'contiene alguna' },
    { value: 'contains_all', label: 'contiene todas' },
    { value: 'is_empty', label: 'vacío' },
    { value: 'is_not_empty', label: 'no vacío' },
  ],
  text: [
    { value: 'eq', label: '=' },
    { value: 'in', label: 'en lista' },
    { value: 'is_null', label: 'no tiene' },
    { value: 'is_not_null', label: 'tiene' },
  ],
};

function fieldKind(field) {
  return FIELD_OPTIONS.find((f) => f.value === field)?.kind || 'text';
}

function defaultRule() {
  return { field: 'last_appointment_at', op: 'lt_days_ago', value: 60 };
}

function rulesToConditions(rules) {
  if (!rules || typeof rules !== 'object') return { joiner: 'all_of', items: [] };
  if (Array.isArray(rules.all_of)) return { joiner: 'all_of', items: rules.all_of };
  if (Array.isArray(rules.any_of)) return { joiner: 'any_of', items: rules.any_of };
  return { joiner: 'all_of', items: [] };
}

function conditionsToRules(joiner, items) {
  const cleaned = items
    .filter((c) => c && c.field && c.op)
    .map((c) => {
      const out = { field: c.field, op: c.op };
      if (c.value !== undefined && c.value !== '' && c.value !== null) {
        out.value = c.value;
      }
      return out;
    });
  if (!cleaned.length) return {};
  return { [joiner]: cleaned };
}

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return value;
  }
}

function RuleEditor({ rule, onChange, onRemove }) {
  const kind = fieldKind(rule.field);
  const operators = OPERATORS_BY_KIND[kind] || OPERATORS_BY_KIND.text;
  return (
    <div className="rule-row" style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginBottom: '0.4rem' }}>
      <select
        value={rule.field}
        onChange={(e) => {
          const nextKind = fieldKind(e.target.value);
          const nextOp = (OPERATORS_BY_KIND[nextKind] || OPERATORS_BY_KIND.text)[0].value;
          onChange({ ...rule, field: e.target.value, op: nextOp, value: '' });
        }}
      >
        {FIELD_OPTIONS.map((f) => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>
      <select
        value={rule.op}
        onChange={(e) => onChange({ ...rule, op: e.target.value })}
      >
        {operators.map((op) => (
          <option key={op.value} value={op.value}>{op.label}</option>
        ))}
      </select>
      {!['is_null', 'is_not_null', 'is_empty', 'is_not_empty'].includes(rule.op) ? (
        <input
          type={kind === 'number' || rule.op?.endsWith('_days_ago') ? 'number' : 'text'}
          value={rule.value ?? ''}
          onChange={(e) => onChange({ ...rule, value: kind === 'number' || rule.op?.endsWith('_days_ago') ? Number(e.target.value) : e.target.value })}
          placeholder={['contains_any', 'contains_all', 'in', 'between'].includes(rule.op) ? 'separa con coma' : 'valor'}
          onBlur={(e) => {
            if (['contains_any', 'contains_all', 'in', 'between'].includes(rule.op)) {
              const parts = String(e.target.value).split(',').map((s) => s.trim()).filter(Boolean);
              const cast = rule.op === 'between' ? parts.map(Number) : parts;
              onChange({ ...rule, value: cast });
            }
          }}
        />
      ) : null}
      <button type="button" className="danger-action" onClick={onRemove}>Quitar</button>
    </div>
  );
}

export function SegmentsModule({ module, session, tenant }) {
  const tenantId = tenant?.id;
  const [segments, setSegments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formMode, setFormMode] = useState('create');
  const [form, setForm] = useState(initialForm());
  const [preview, setPreview] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  const selected = useMemo(
    () => segments.find((s) => s.id === selectedId) || null,
    [segments, selectedId],
  );

  function initialForm() {
    return {
      name: '',
      description: '',
      kind: 'dynamic',
      joiner: 'all_of',
      items: [defaultRule()],
    };
  }

  function refreshSegments() {
    if (!tenantId) return Promise.resolve();
    return listContactSegments(session, tenantId)
      .then((items) => {
        setSegments(items || []);
        if (items?.length && !items.some((s) => s.id === selectedId)) {
          setSelectedId(items[0].id);
        } else if (!items?.length) {
          setSelectedId(null);
        }
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  useEffect(() => {
    if (!tenantId) return;
    refreshSegments();
  }, [tenantId]);

  function startCreate() {
    setFormMode('create');
    setForm(initialForm());
    setPreview(null);
    setShowForm(true);
  }

  function startEdit(segment) {
    if (!segment) return;
    setFormMode('edit');
    const { joiner, items } = rulesToConditions(segment.rules || {});
    setForm({
      name: segment.name || '',
      description: segment.description || '',
      kind: segment.kind || 'dynamic',
      joiner,
      items: items.length ? items : [defaultRule()],
    });
    setPreview(null);
    setShowForm(true);
  }

  function buildPayload() {
    return {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      kind: form.kind,
      rules: form.kind === 'dynamic' ? conditionsToRules(form.joiner, form.items) : {},
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!form.name.trim()) {
      setNotice({ type: 'error', text: 'El nombre es obligatorio.' });
      return;
    }
    setIsBusy(true);
    try {
      const payload = buildPayload();
      let saved;
      if (formMode === 'create') {
        saved = await createContactSegment(session, tenantId, payload);
      } else {
        saved = await updateContactSegment(session, tenantId, selectedId, payload);
      }
      setNotice({ type: 'success', text: 'Segmento guardado.' });
      await refreshSegments();
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
      const data = await previewContactSegment(session, tenantId, selectedId, { limit: 25 });
      setPreview(data);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRefresh() {
    if (!selectedId) return;
    setIsBusy(true);
    try {
      await refreshContactSegment(session, tenantId, selectedId);
      setNotice({ type: 'success', text: 'Segmento recalculado.' });
      await refreshSegments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDelete() {
    if (!selectedId || !selected) return;
    if (selected.is_system) {
      setNotice({ type: 'error', text: 'Los segmentos del sistema no se eliminan.' });
      return;
    }
    if (!window.confirm(`¿Eliminar el segmento "${selected.name}"?`)) return;
    setIsBusy(true);
    try {
      await deleteContactSegment(session, tenantId, selectedId);
      setSelectedId(null);
      setPreview(null);
      await refreshSegments();
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  if (!tenantId) {
    return (
      <section className="module-card">
        <div className="module-heading">
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <p className="hint">Selecciona un tenant para gestionar segmentos.</p>
      </section>
    );
  }

  return (
    <section className="module-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Retención y reactivación</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="form-actions">
          <button className="primary-action" type="button" onClick={startCreate} disabled={isBusy}>
            Nuevo segmento
          </button>
        </div>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      <div className="operations-layout" style={{ marginTop: '1rem' }}>
        <aside className="conversation-list" aria-label="Segmentos">
          {segments.length === 0 ? <p className="hint">No hay segmentos todavía.</p> : null}
          {segments.map((segment) => (
            <button
              type="button"
              key={segment.id}
              className={`conversation-card ${segment.id === selectedId ? 'active' : ''}`}
              onClick={() => {
                setSelectedId(segment.id);
                setShowForm(false);
                setPreview(null);
              }}
            >
              <span>{segment.name}</span>
              <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                <small>{KIND_LABELS[segment.kind] || segment.kind}</small>
                <small>· {segment.contact_count} contactos</small>
                {segment.is_system ? <small>· sistema</small> : null}
              </div>
              <small>Refrescado: {formatDate(segment.last_refreshed_at)}</small>
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
                  placeholder="Reactivación 60+ días"
                />
              </label>
              <label>
                Descripción
                <input
                  value={form.description}
                  onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                  placeholder="Opcional"
                />
              </label>
              <label>
                Tipo
                <select
                  value={form.kind}
                  onChange={(e) => setForm((p) => ({ ...p, kind: e.target.value }))}
                >
                  <option value="dynamic">{KIND_LABELS.dynamic}</option>
                  <option value="static">{KIND_LABELS.static}</option>
                </select>
              </label>
              {form.kind === 'dynamic' ? (
                <fieldset style={{ gridColumn: '1 / -1', border: '1px solid var(--border, #e2e8f0)', borderRadius: 8, padding: '0.8rem' }}>
                  <legend>Reglas</legend>
                  <label>
                    Combinador
                    <select
                      value={form.joiner}
                      onChange={(e) => setForm((p) => ({ ...p, joiner: e.target.value }))}
                    >
                      <option value="all_of">Todas (AND)</option>
                      <option value="any_of">Alguna (OR)</option>
                    </select>
                  </label>
                  <div style={{ marginTop: '0.6rem' }}>
                    {form.items.map((rule, idx) => (
                      <RuleEditor
                        key={idx}
                        rule={rule}
                        onChange={(next) =>
                          setForm((p) => ({
                            ...p,
                            items: p.items.map((r, i) => (i === idx ? next : r)),
                          }))
                        }
                        onRemove={() =>
                          setForm((p) => ({
                            ...p,
                            items: p.items.filter((_, i) => i !== idx),
                          }))
                        }
                      />
                    ))}
                    <button
                      type="button"
                      className="secondary-action"
                      onClick={() =>
                        setForm((p) => ({ ...p, items: [...p.items, defaultRule()] }))
                      }
                    >
                      Añadir regla
                    </button>
                  </div>
                </fieldset>
              ) : null}
              <div className="form-actions" style={{ gridColumn: '1 / -1' }}>
                <button className="secondary-action" type="button" onClick={() => setShowForm(false)}>
                  Cancelar
                </button>
                <button className="primary-action" type="submit" disabled={isBusy}>
                  {formMode === 'create' ? 'Crear segmento' : 'Guardar cambios'}
                </button>
              </div>
            </form>
          ) : !selected ? (
            <div className="empty-detail">
              <h3>Selecciona o crea un segmento</h3>
              <p className="hint">
                Los segmentos permiten reutilizar reglas (ej. "Sin visita en 60+ días") como destinatarios de
                campañas y filtros de contactos. Tu tenant ya viene con 5 segmentos preconfigurados.
              </p>
            </div>
          ) : (
            <>
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Segmento {KIND_LABELS[selected.kind] || selected.kind}</p>
                  <h3>{selected.name}</h3>
                  {selected.description ? <p className="hint">{selected.description}</p> : null}
                  <p className="hint">
                    <strong>{selected.contact_count}</strong> contactos · refrescado {formatDate(selected.last_refreshed_at)}
                  </p>
                </div>
                <div className="form-actions">
                  <button className="secondary-action" type="button" onClick={() => startEdit(selected)} disabled={isBusy}>
                    Editar
                  </button>
                  <button className="secondary-action" type="button" onClick={handlePreview} disabled={isBusy}>
                    Previsualizar
                  </button>
                  {selected.kind === 'dynamic' ? (
                    <button className="secondary-action" type="button" onClick={handleRefresh} disabled={isBusy}>
                      Refrescar ahora
                    </button>
                  ) : null}
                  {!selected.is_system ? (
                    <button className="danger-action" type="button" onClick={handleDelete} disabled={isBusy}>
                      Eliminar
                    </button>
                  ) : null}
                </div>
              </div>

              {preview ? (
                <div className="schedule-panel">
                  <strong>Muestra: {preview.contact_count} contactos</strong>
                  {preview.sample?.length ? (
                    <ul style={{ listStyle: 'none', padding: 0, margin: '0.4rem 0 0' }}>
                      {preview.sample.map((c) => (
                        <li key={c.contact_id} style={{ padding: '0.3rem 0', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <strong>{c.display_name || c.phone_e164}</strong>
                          <div className="hint" style={{ fontSize: '0.8rem' }}>
                            {c.phone_e164} · opt-in: {c.opt_in_status}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="hint">Ningún contacto cumple las reglas actualmente.</p>
                  )}
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </section>
  );
}
