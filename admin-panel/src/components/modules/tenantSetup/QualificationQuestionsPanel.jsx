import { useEffect, useMemo, useState } from 'react';

import {
  createQualificationQuestion,
  deleteQualificationQuestion,
  listQualificationQuestions,
  listServices,
  reorderQualificationQuestions,
  updateQualificationQuestion,
} from '../../../services/coreApi.js';

const KIND_OPTIONS = [
  { value: 'yes_no', label: 'Sí / No' },
  { value: 'single_choice', label: 'Opción única (botones / lista)' },
  { value: 'multi_choice', label: 'Opciones múltiples (lista)' },
  { value: 'free_text', label: 'Texto libre' },
  { value: 'number', label: 'Número' },
];

const CHOICE_KINDS = new Set(['single_choice', 'multi_choice']);

const PRESET_BUDGET_TIER = 'budget_tier';
const PRESET_URGENCY_LEVEL = 'urgency_level';

const BUDGET_TIER_PRESET = {
  label: '¿En qué rango de presupuesto te ubicas?',
  kind: 'single_choice',
  required: true,
  preset: PRESET_BUDGET_TIER,
  options: [
    { value: 'low', label: 'Menos de $200.000', tier_value: 200000 },
    { value: 'mid', label: '$200.000 – $800.000', tier_value: 800000 },
    { value: 'high', label: 'Más de $800.000', tier_value: 1000000 },
  ],
};

const URGENCY_LEVEL_PRESET = {
  label: '¿Qué tan urgente es tu caso?',
  kind: 'single_choice',
  required: true,
  preset: PRESET_URGENCY_LEVEL,
  options: [
    { value: 'emergency', label: '🚨 Emergencia', urgency_normalized: 'emergency' },
    { value: 'high', label: 'Alta', urgency_normalized: 'high' },
    { value: 'normal', label: 'Normal', urgency_normalized: 'normal' },
    { value: 'low', label: 'Cuando se pueda', urgency_normalized: 'low' },
  ],
};

function emptyForm() {
  return {
    label: '',
    kind: 'yes_no',
    options: [],
    required: true,
    applies_to_service_ids: [],
    preset: null,
  };
}

function presetForm(preset) {
  if (preset === PRESET_BUDGET_TIER) {
    return {
      label: BUDGET_TIER_PRESET.label,
      kind: BUDGET_TIER_PRESET.kind,
      options: BUDGET_TIER_PRESET.options.map((o) => ({ ...o })),
      required: BUDGET_TIER_PRESET.required,
      applies_to_service_ids: [],
      preset: PRESET_BUDGET_TIER,
    };
  }
  if (preset === PRESET_URGENCY_LEVEL) {
    return {
      label: URGENCY_LEVEL_PRESET.label,
      kind: URGENCY_LEVEL_PRESET.kind,
      options: URGENCY_LEVEL_PRESET.options.map((o) => ({ ...o })),
      required: URGENCY_LEVEL_PRESET.required,
      applies_to_service_ids: [],
      preset: PRESET_URGENCY_LEVEL,
    };
  }
  return emptyForm();
}

function previewQuestion(question) {
  if (!question) return null;
  if (question.kind === 'yes_no') {
    return ['Sí', 'No'];
  }
  if (CHOICE_KINDS.has(question.kind)) {
    return (question.options || []).map((opt) => opt.label || opt.value);
  }
  if (question.kind === 'number') {
    return ['(el cliente responde con un número)'];
  }
  return ['(el cliente responde con texto libre)'];
}

export default function QualificationQuestionsPanel({ session, tenantId, onNotice }) {
  const [questions, setQuestions] = useState([]);
  const [services, setServices] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm());

  const reload = async () => {
    if (!tenantId) return;
    setIsLoading(true);
    try {
      const [qs, svc] = await Promise.all([
        listQualificationQuestions(session, tenantId),
        listServices(session, tenantId, { includeInactive: false }),
      ]);
      setQuestions(qs || []);
      setServices(svc || []);
    } catch (error) {
      onNotice?.({ type: 'error', text: `No se pudieron cargar las preguntas: ${error.message}` });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  const servicesById = useMemo(() => {
    const map = new Map();
    services.forEach((s) => map.set(s.id, s));
    return map;
  }, [services]);

  const startNew = () => {
    setEditingId(null);
    setForm(emptyForm());
  };

  const startEdit = (question) => {
    setEditingId(question.id);
    setForm({
      label: question.label || '',
      kind: question.kind,
      options: Array.isArray(question.options)
        ? question.options.map((o) => ({
            value: o.value || '',
            label: o.label || '',
            service_id: o.service_id || '',
            tier_value: o.tier_value ?? '',
            urgency_normalized: o.urgency_normalized || '',
          }))
        : [],
      required: question.required !== false,
      applies_to_service_ids: question.applies_to_service_ids || [],
      preset: question.preset || null,
    });
  };

  const insertPreset = (preset) => {
    setEditingId(null);
    setForm(presetForm(preset));
  };

  const updateOption = (idx, key, value) => {
    setForm((prev) => {
      const next = [...prev.options];
      next[idx] = { ...next[idx], [key]: value };
      return { ...prev, options: next };
    });
  };

  const addOption = () => {
    setForm((prev) => ({
      ...prev,
      options: [...prev.options, { value: '', label: '', service_id: '' }],
    }));
  };

  const removeOption = (idx) => {
    setForm((prev) => ({
      ...prev,
      options: prev.options.filter((_, i) => i !== idx),
    }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!tenantId) return;
    if (!form.label.trim()) {
      onNotice?.({ type: 'error', text: 'La pregunta no puede estar vacía.' });
      return;
    }
    const cleanedOptions = CHOICE_KINDS.has(form.kind)
      ? form.options
          .filter((o) => o.value.trim() && o.label.trim())
          .map((o) => {
            const opt = { value: o.value.trim(), label: o.label.trim() };
            if (o.service_id) opt.service_id = o.service_id;
            if (o.tier_value !== '' && o.tier_value != null) {
              const tv = Number(o.tier_value);
              if (Number.isFinite(tv) && tv >= 0) opt.tier_value = tv;
            }
            if (o.urgency_normalized) opt.urgency_normalized = o.urgency_normalized;
            return opt;
          })
      : [];
    if (CHOICE_KINDS.has(form.kind) && cleanedOptions.length === 0) {
      onNotice?.({ type: 'error', text: 'Agrega al menos una opción.' });
      return;
    }
    const payload = {
      label: form.label.trim(),
      kind: form.kind,
      options: cleanedOptions,
      required: form.required,
      applies_to_service_ids: form.applies_to_service_ids,
      preset: form.preset || null,
    };
    setIsBusy(true);
    try {
      if (editingId) {
        await updateQualificationQuestion(session, tenantId, editingId, payload);
        onNotice?.({ type: 'success', text: 'Pregunta actualizada.' });
      } else {
        payload.position = questions.length;
        await createQualificationQuestion(session, tenantId, payload);
        onNotice?.({ type: 'success', text: 'Pregunta agregada.' });
      }
      startNew();
      await reload();
    } catch (error) {
      onNotice?.({ type: 'error', text: `No se pudo guardar: ${error.message}` });
    } finally {
      setIsBusy(false);
    }
  };

  const remove = async (question) => {
    if (!window.confirm(`¿Eliminar la pregunta "${question.label}"?`)) return;
    setIsBusy(true);
    try {
      await deleteQualificationQuestion(session, tenantId, question.id);
      onNotice?.({ type: 'success', text: 'Pregunta eliminada.' });
      if (editingId === question.id) startNew();
      await reload();
    } catch (error) {
      onNotice?.({ type: 'error', text: `No se pudo eliminar: ${error.message}` });
    } finally {
      setIsBusy(false);
    }
  };

  const move = async (idx, delta) => {
    const target = idx + delta;
    if (target < 0 || target >= questions.length) return;
    const reordered = [...questions];
    const [item] = reordered.splice(idx, 1);
    reordered.splice(target, 0, item);
    const order = reordered.map((q, i) => ({ id: q.id, position: i }));
    setIsBusy(true);
    try {
      await reorderQualificationQuestions(session, tenantId, order);
      await reload();
    } catch (error) {
      onNotice?.({ type: 'error', text: `No se pudo reordenar: ${error.message}` });
    } finally {
      setIsBusy(false);
    }
  };

  if (!tenantId) {
    return (
      <p className="hint">
        Crea o selecciona un tenant antes de configurar la calificación previa al booking.
      </p>
    );
  }

  return (
    <div className="qualification-panel">
      <h3>Calificación previa al booking</h3>
      <p className="hint">
        Estas preguntas se envían al cliente <strong>antes</strong> de la selección de servicio
        cuando expresa intención de agendar. Sirven para entender el motivo, urgencia y derivar
        al servicio correcto sin trabajo manual.
      </p>

      <div className="qualification-list">
        {isLoading ? (
          <p className="hint">Cargando…</p>
        ) : questions.length === 0 ? (
          <p className="hint">Aún no hay preguntas configuradas.</p>
        ) : (
          <ul className="qualification-items">
            {questions.map((q, idx) => {
              const preview = previewQuestion(q);
              return (
                <li className="qualification-card" key={q.id}>
                  <div className="qualification-card-head">
                    <div>
                      <strong>{idx + 1}. {q.label}</strong>
                      <span className="qualification-kind">{KIND_OPTIONS.find((o) => o.value === q.kind)?.label || q.kind}</span>
                      {q.required ? <span className="qualification-required">Obligatoria</span> : null}
                    </div>
                    <div className="qualification-actions">
                      <button
                        type="button"
                        className="drag-handle"
                        onClick={() => move(idx, -1)}
                        disabled={idx === 0 || isBusy}
                        aria-label="Subir"
                      >↑</button>
                      <button
                        type="button"
                        className="drag-handle"
                        onClick={() => move(idx, +1)}
                        disabled={idx === questions.length - 1 || isBusy}
                        aria-label="Bajar"
                      >↓</button>
                      <button type="button" onClick={() => startEdit(q)} disabled={isBusy}>
                        Editar
                      </button>
                      <button type="button" className="danger" onClick={() => remove(q)} disabled={isBusy}>
                        Eliminar
                      </button>
                    </div>
                  </div>
                  {preview ? (
                    <ul className="qualification-preview">
                      {preview.map((p, i) => (
                        <li key={i}>· {p}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="qualification-presets" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
        <button
          type="button"
          className="secondary-action"
          onClick={() => insertPreset(PRESET_BUDGET_TIER)}
          disabled={isBusy}
        >
          Insertar pregunta de presupuesto
        </button>
        <button
          type="button"
          className="secondary-action"
          onClick={() => insertPreset(PRESET_URGENCY_LEVEL)}
          disabled={isBusy}
        >
          Insertar pregunta de urgencia
        </button>
      </div>

      <form className="qualification-form form-grid" onSubmit={submit}>
        <h4>
          {editingId ? 'Editar pregunta' : 'Nueva pregunta'}
          {form.preset === PRESET_BUDGET_TIER ? ' · preset Presupuesto' : null}
          {form.preset === PRESET_URGENCY_LEVEL ? ' · preset Urgencia' : null}
        </h4>
        <label>
          Pregunta
          <input
            type="text"
            value={form.label}
            onChange={(event) => setForm({ ...form, label: event.target.value })}
            placeholder="Ej. ¿Cuál es el motivo de tu consulta?"
            maxLength={200}
            required
          />
        </label>
        <label>
          Tipo
          <select
            value={form.kind}
            onChange={(event) => setForm({ ...form, kind: event.target.value, options: [] })}
          >
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.required}
            onChange={(event) => setForm({ ...form, required: event.target.checked })}
          />
          La respuesta es obligatoria
        </label>

        {CHOICE_KINDS.has(form.kind) ? (
          <div className="qualification-options">
            <strong>Opciones</strong>
            {form.options.map((opt, idx) => (
              <div className="option-row" key={idx}>
                <input
                  type="text"
                  placeholder="Valor interno (sin espacios)"
                  value={opt.value}
                  onChange={(event) => updateOption(idx, 'value', event.target.value)}
                  maxLength={120}
                />
                <input
                  type="text"
                  placeholder="Texto visible al cliente"
                  value={opt.label}
                  onChange={(event) => updateOption(idx, 'label', event.target.value)}
                  maxLength={120}
                />
                <select
                  value={opt.service_id || ''}
                  onChange={(event) => updateOption(idx, 'service_id', event.target.value)}
                >
                  <option value="">Sin derivar a servicio</option>
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      Derivar a: {service.name}
                    </option>
                  ))}
                </select>
                {form.preset === PRESET_BUDGET_TIER ? (
                  <input
                    type="number"
                    min="0"
                    step="1000"
                    placeholder="Valor numérico del tier"
                    value={opt.tier_value ?? ''}
                    onChange={(event) => updateOption(idx, 'tier_value', event.target.value)}
                  />
                ) : null}
                {form.preset === PRESET_URGENCY_LEVEL ? (
                  <select
                    value={opt.urgency_normalized || ''}
                    onChange={(event) => updateOption(idx, 'urgency_normalized', event.target.value)}
                  >
                    <option value="">— Nivel normalizado —</option>
                    <option value="emergency">emergency</option>
                    <option value="high">high</option>
                    <option value="normal">normal</option>
                    <option value="low">low</option>
                  </select>
                ) : null}
                <button type="button" className="danger" onClick={() => removeOption(idx)}>
                  Quitar
                </button>
              </div>
            ))}
            <button type="button" onClick={addOption}>+ Agregar opción</button>
          </div>
        ) : null}

        <div className="form-actions">
          {editingId ? (
            <button type="button" onClick={startNew} disabled={isBusy}>
              Cancelar
            </button>
          ) : null}
          <button className="primary-action" type="submit" disabled={isBusy}>
            {editingId ? 'Guardar cambios' : 'Agregar pregunta'}
          </button>
        </div>
      </form>
    </div>
  );
}
