/**
 * UI-INFLU-010 — Wizard Paso 3: Identidad.
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader, Stepper } from '../../../components/ui/index.js';
import {
  CATEGORIES,
  DESCRIPTION_MAX,
  buildIdentityPayload,
  previewCardData,
  validateHandle,
} from './step3IdentityData.js';


const STEPS = [
  { id: 'face', label: 'Cara', state: 'complete' },
  { id: 'body', label: 'Cuerpo', state: 'complete' },
  { id: 'identity', label: 'Identidad', state: 'current' },
  { id: 'voice', label: 'Voz', state: 'upcoming' },
  { id: 'platforms', label: 'Plataformas', state: 'upcoming' },
];


export function Step3Identity({ initialForm = {}, onNext, onSaveDraft, onCheckHandle }) {
  const [form, setForm] = useState({
    name: '', handle: '', age: 25, city: '', country: '',
    languages: [], brands: [], categories: [], description: '', ...initialForm,
  });
  const [error, setError] = useState(null);
  const [handleError, setHandleError] = useState(null);

  const update = (key, value) => setForm((p) => ({ ...p, [key]: value }));

  const addChip = (key, value) => {
    if (!value) return;
    const next = Array.from(new Set([...(form[key] || []), value]));
    update(key, next);
  };
  const removeChip = (key, value) => {
    update(key, (form[key] || []).filter((c) => c !== value));
  };

  const handleNext = async () => {
    if (!form.name.trim()) {
      setError('Nombre requerido');
      return;
    }
    const v = validateHandle(form.handle);
    if (!v.valid) {
      setHandleError(v.error);
      return;
    }
    if (onCheckHandle) {
      const taken = await onCheckHandle(v.normalized);
      if (taken) {
        setHandleError('Handle ya en uso');
        return;
      }
    }
    setError(null);
    setHandleError(null);
    onNext?.(buildIdentityPayload(form));
  };

  const preview = previewCardData(form);

  return (
    <div data-module="influencer" data-view="wizard-step-3">
      <PageHeader eyebrow="Crear personaje · Paso 3 de 5" title="Identidad" />
      <Stepper steps={STEPS} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
        <div>
          <Card padding="md">
            <label style={{ display: 'block' }}>
              <span style={{ fontWeight: 600 }}>Nombre *</span>
              <input value={form.name} onChange={(e) => update('name', e.target.value)} style={{ width: '100%' }} />
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <span style={{ fontWeight: 600 }}>Handle *</span>
              <input
                value={form.handle}
                onChange={(e) => { update('handle', e.target.value); setHandleError(null); }}
                placeholder="sofia.studio"
                style={{ width: '100%' }}
                aria-invalid={!!handleError}
              />
              {handleError && (
                <span style={{ color: 'var(--color-danger-fg, #b91c1c)', fontSize: 12 }}>{handleError}</span>
              )}
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <span style={{ fontWeight: 600 }}>Edad</span>
              <input type="number" min="18" max="99" value={form.age} onChange={(e) => update('age', Number(e.target.value))} />
            </label>
          </Card>

          <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
            <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Ubicación</div>
            <label style={{ display: 'block' }}>
              <span>Ciudad</span>
              <input value={form.city} onChange={(e) => update('city', e.target.value)} />
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-1)' }}>
              <span>País</span>
              <input value={form.country} onChange={(e) => update('country', e.target.value)} />
            </label>
          </Card>

          <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
            <ChipField
              label="Brands"
              values={form.brands}
              onAdd={(v) => addChip('brands', v)}
              onRemove={(v) => removeChip('brands', v)}
            />
            <div style={{ marginTop: 'var(--space-3)' }}>
              <div style={{ fontWeight: 600 }}>Categorías</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', marginTop: 'var(--space-1)' }}>
                {CATEGORIES.map((cat) => {
                  const active = (form.categories || []).includes(cat);
                  return (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => active ? removeChip('categories', cat) : addChip('categories', cat)}
                      aria-pressed={active}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 999,
                        background: active ? 'var(--color-action-primary-bg, #111)' : 'transparent',
                        color: active ? 'var(--color-action-primary-fg, #fff)' : 'inherit',
                        border: '1px solid var(--color-border, #d1d5db)',
                        cursor: 'pointer',
                      }}
                    >{cat}</button>
                  );
                })}
              </div>
            </div>
          </Card>

          <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
            <label style={{ display: 'block' }}>
              <span style={{ fontWeight: 600 }}>Descripción ({form.description.length}/{DESCRIPTION_MAX})</span>
              <textarea
                rows={4}
                value={form.description}
                onChange={(e) => update('description', e.target.value.slice(0, DESCRIPTION_MAX))}
                style={{ width: '100%' }}
              />
            </label>
          </Card>
        </div>

        <aside aria-label="Preview live" style={{ position: 'sticky', top: 16 }}>
          <Card padding="md">
            <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>Preview</div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{form.name || 'Tu personaje'}</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-subtle, #6b7280)' }}>
              {preview.handle || '@handle'}
              {preview.location && ` · ${preview.location}`}
            </div>
            {preview.description && (
              <p style={{ marginTop: 'var(--space-2)' }}>{preview.description}</p>
            )}
            <div style={{ marginTop: 'var(--space-2)', display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {(form.categories || []).map((c) => (
                <span key={c} style={{
                  padding: '2px 8px', borderRadius: 999, fontSize: 11,
                  background: 'var(--color-surface-emphasis, #f3f4f6)',
                }}>{c}</span>
              ))}
            </div>
          </Card>
        </aside>
      </div>

      {error && <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 'var(--space-4)',
      }}>
        <span>Paso 3 de 5</span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button type="button" onClick={() => onSaveDraft?.(buildIdentityPayload(form))}>
            Guardar borrador
          </button>
          <button type="button" onClick={handleNext}>Siguiente paso</button>
        </div>
      </div>
    </div>
  );
}


function ChipField({ label, values, onAdd, onRemove }) {
  const [input, setInput] = useState('');
  const submit = () => {
    if (input.trim()) {
      onAdd(input.trim());
      setInput('');
    }
  };
  return (
    <div>
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div style={{ display: 'flex', gap: 'var(--space-1)', marginTop: 'var(--space-1)' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }}
          aria-label={`Agregar ${label}`}
          style={{ flex: 1 }}
        />
        <button type="button" onClick={submit}>Agregar</button>
      </div>
      <ul style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', listStyle: 'none', margin: 'var(--space-1) 0 0', padding: 0 }}>
        {(values || []).map((v) => (
          <li key={v} style={{
            padding: '2px 8px',
            borderRadius: 999,
            background: 'var(--color-surface-emphasis, #f3f4f6)',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            {v}
            <button
              type="button"
              onClick={() => onRemove(v)}
              aria-label={`Eliminar ${v}`}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 700 }}
            >×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
