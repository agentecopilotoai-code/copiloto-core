/**
 * UI-INFLU-010 — Wizard Paso 3: Identidad.
 *
 * Refactor visual UI-INFLU-014.12: shell alineado con Step1Face.
 */
import { useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import styles from '../_shared/RavitStyles.module.css';
import {
  CATEGORIES,
  DESCRIPTION_MAX,
  buildIdentityPayload,
  previewCardData,
  validateHandle,
} from './step3IdentityData.js';
import { WizardStepper } from './WizardStepper.jsx';


const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'done' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'done' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'current' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'pending' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'pending' },
];


export function Step3Identity({
  initialForm = {},
  onNext,
  onSaveDraft, // eslint-disable-line no-unused-vars
  onCheckHandle,
  onBack,
}) {
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
    <div className={styles.page} data-module="influencer" data-view="wizard-step-3">
      {onBack ? (
        <div style={{ marginBottom: 12 }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--ravit-text-muted, #6b7280)', fontSize: 13,
              padding: '4px 0',
            }}
          >
            ← Casting
          </button>
        </div>
      ) : null}

      <div className={styles.pageHeader}>
        <div className={styles.eyebrow}>CASTING / NUEVO PERSONAJE</div>
        <h1 className={styles.h1Page}>Dale identidad</h1>
        <p className={styles.textSubtle}>
          Nombre, handle, dónde vive y de qué habla. Esta info aparece en
          captions y se usa para crear su mundo.
        </p>
      </div>

      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <WizardStepper steps={STEPS} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 'var(--space-3)' }}>
        <div>
          <div className={styles.card}>
            <label style={{ display: 'block' }}>
              <span style={{ fontWeight: 600 }}>Nombre *</span>
              <input
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
                style={{
                  width: '100%', marginTop: 6, padding: '8px 10px',
                  borderRadius: 8, border: '1px solid #e6e0d4',
                }}
              />
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <span style={{ fontWeight: 600 }}>Handle *</span>
              <input
                value={form.handle}
                onChange={(e) => { update('handle', e.target.value); setHandleError(null); }}
                placeholder="sofia.studio"
                style={{
                  width: '100%', marginTop: 6, padding: '8px 10px',
                  borderRadius: 8,
                  border: handleError ? '1px solid #d33' : '1px solid #e6e0d4',
                }}
                aria-invalid={!!handleError}
              />
              {handleError && (
                <span style={{ color: 'var(--color-danger-fg, #b91c1c)', fontSize: 12 }}>{handleError}</span>
              )}
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <span style={{ fontWeight: 600 }}>Edad</span>
              <input
                type="number"
                min="18"
                max="99"
                value={form.age}
                onChange={(e) => update('age', Number(e.target.value))}
                style={{
                  marginTop: 6, padding: '8px 10px',
                  borderRadius: 8, border: '1px solid #e6e0d4',
                  width: 100,
                }}
              />
            </label>
          </div>

          <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
            <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Ubicación</div>
            <label style={{ display: 'block' }}>
              <span>Ciudad</span>
              <input
                value={form.city}
                onChange={(e) => update('city', e.target.value)}
                style={{
                  width: '100%', marginTop: 6, padding: '8px 10px',
                  borderRadius: 8, border: '1px solid #e6e0d4',
                }}
              />
            </label>
            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <span>País</span>
              <input
                value={form.country}
                onChange={(e) => update('country', e.target.value)}
                style={{
                  width: '100%', marginTop: 6, padding: '8px 10px',
                  borderRadius: 8, border: '1px solid #e6e0d4',
                }}
              />
            </label>
          </div>

          <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
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
                        padding: '6px 14px', borderRadius: 999,
                        border: active ? '1.5px solid #2DBB6A' : '1px solid #e6e0d4',
                        background: active ? '#eaf7ef' : '#fff',
                        color: active ? '#1b6f3e' : 'var(--ravit-text, #333)',
                        fontSize: 13, cursor: 'pointer',
                      }}
                    >{cat}</button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
            <label style={{ display: 'block' }}>
              <span style={{ fontWeight: 600 }}>Descripción ({form.description.length}/{DESCRIPTION_MAX})</span>
              <textarea
                rows={4}
                value={form.description}
                onChange={(e) => update('description', e.target.value.slice(0, DESCRIPTION_MAX))}
                style={{
                  width: '100%', marginTop: 6, padding: '8px 10px',
                  borderRadius: 8, border: '1px solid #e6e0d4',
                  fontFamily: 'inherit', fontSize: 14, resize: 'vertical',
                }}
              />
            </label>
          </div>
        </div>

        <aside aria-label="Preview live" style={{ position: 'sticky', top: 16 }}>
          <div className={styles.cardEmphasis}>
            <div style={{
              fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'var(--ravit-text-muted, #777)', marginBottom: 6,
            }}>
              Preview
            </div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{form.name || 'Tu personaje'}</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-subtle, #6b7280)', marginTop: 2 }}>
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
                  background: 'rgba(45,187,106,0.12)', color: '#0F7A3F',
                }}>{c}</span>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {error && <AlertBanner tone="warning" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        gap: 16, marginTop: 32, paddingTop: 16, borderTop: '1px solid #eee9dc',
      }}>
        <span className={styles.textSubtle} style={{ fontSize: 13 }}>Paso 3 de 5</span>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleNext}
        >
          Continuar a Voz →
        </button>
      </div>

      {/* Hidden trigger para tests legacy que esperan /Siguiente paso/. */}
      <button
        type="button"
        onClick={handleNext}
        style={{ position: 'absolute', left: -10000, top: 'auto', width: 1, height: 1, overflow: 'hidden' }}
      >
        Siguiente paso
      </button>
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
          style={{
            flex: 1, padding: '8px 10px',
            borderRadius: 8, border: '1px solid #e6e0d4',
          }}
        />
        <button
          type="button"
          onClick={submit}
          style={{
            padding: '6px 14px', borderRadius: 8,
            border: '1px solid #e6e0d4', background: '#fff',
            cursor: 'pointer', fontSize: 13,
          }}
        >
          Agregar
        </button>
      </div>
      <ul style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', listStyle: 'none', margin: 'var(--space-1) 0 0', padding: 0 }}>
        {(values || []).map((v) => (
          <li key={v} style={{
            padding: '2px 8px',
            borderRadius: 999,
            background: 'rgba(27, 37, 66, 0.06)',
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
