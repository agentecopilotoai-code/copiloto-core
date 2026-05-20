/**
 * UI-INFLU-008 — Wizard Paso 1: Cara.
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader, Stepper } from '../../../components/ui/index.js';
import {
  FACE_OPTIONS,
  buildFacePayload,
  canonicalFromVariations,
  defaultsForRandom,
  validateMinimum,
} from './step1FaceData.js';


const STEPS = [
  { id: 'face', label: 'Cara', state: 'current' },
  { id: 'body', label: 'Cuerpo', state: 'upcoming' },
  { id: 'identity', label: 'Identidad', state: 'upcoming' },
  { id: 'voice', label: 'Voz', state: 'upcoming' },
  { id: 'platforms', label: 'Plataformas', state: 'upcoming' },
];


export function Step1Face({
  onNext,
  onSaveDraft,
  onGenerateVariations,
  initialForm = {},
  initialVariations = [],
}) {
  const [form, setForm] = useState({ starting_point: 'upload', ...initialForm });
  const [variations, setVariations] = useState(initialVariations);
  const [error, setError] = useState(null);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleStartingPoint = (sp) => {
    if (sp === 'random') {
      setForm(defaultsForRandom());
    } else {
      update('starting_point', sp);
    }
  };

  const handleGenerate = async () => {
    const { valid, missing } = validateMinimum(form);
    if (!valid) {
      setError(`Faltan: ${missing.join(', ')}`);
      return;
    }
    setError(null);
    const result = await onGenerateVariations?.(buildFacePayload(form));
    if (Array.isArray(result?.variations)) {
      setVariations(result.variations);
    }
  };

  const handleNext = () => {
    const canonical = variations.find((v) => v.canonical);
    if (!canonical) {
      setError('Selecciona una variación como canonical antes de continuar.');
      return;
    }
    onNext?.({
      ...buildFacePayload(form),
      canonical_asset_id: canonical.id,
    });
  };

  const selectCanonical = (id) => setVariations(canonicalFromVariations(variations, id));

  return (
    <div data-module="influencer" data-view="wizard-step-1">
      <PageHeader eyebrow="Crear personaje · Paso 1 de 5" title="Cara" />
      <Stepper steps={STEPS} />

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <fieldset>
          <legend style={{ fontWeight: 600 }}>Punto de partida</legend>
          {[
            { value: 'upload', label: 'Subir foto' },
            { value: 'template', label: 'Plantilla (8 caras base)' },
            { value: 'random', label: 'Aleatorio IA al azar' },
          ].map((opt) => (
            <label key={opt.value} style={{ display: 'block', marginTop: 'var(--space-1)' }}>
              <input
                type="radio"
                name="starting_point"
                value={opt.value}
                checked={form.starting_point === opt.value}
                onChange={() => handleStartingPoint(opt.value)}
              />
              <span style={{ marginLeft: 'var(--space-1)' }}>{opt.label}</span>
            </label>
          ))}
        </fieldset>
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <FaceSelectors form={form} onUpdate={update} />
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontWeight: 600 }}>Variaciones generadas</div>
          <button type="button" onClick={handleGenerate}>
            {variations.length ? 'Generar 4 más' : 'Generar 4 variaciones'}
          </button>
        </div>

        {variations.length > 0 ? (
          <ul aria-label="Variaciones" style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
            gap: 'var(--space-2)', marginTop: 'var(--space-2)', padding: 0, listStyle: 'none',
          }}>
            {variations.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  aria-pressed={!!v.canonical}
                  onClick={() => selectCanonical(v.id)}
                  style={{
                    width: '100%', aspectRatio: '1', padding: 0,
                    border: v.canonical ? '3px solid var(--color-action-primary-bg, #111)' : '1px solid var(--color-border, #ccc)',
                    borderRadius: 'var(--radius-md, 6px)',
                    cursor: 'pointer',
                  }}
                >
                  {v.thumbnail_url
                    ? <img src={v.thumbnail_url} alt={`Variación ${v.id}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : v.id}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ marginTop: 'var(--space-2)', color: 'var(--color-text-subtle, #6b7280)' }}>
            Configura los rasgos y genera variaciones.
          </p>
        )}
      </Card>

      {error && (
        <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>
      )}

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 'var(--space-4)',
      }}>
        <span>Paso 1 de 5</span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button type="button" onClick={() => onSaveDraft?.(buildFacePayload(form))}>
            Guardar borrador
          </button>
          <button type="button" onClick={handleNext}>Siguiente paso</button>
        </div>
      </div>
    </div>
  );
}


function FaceSelectors({ form, onUpdate }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
      gap: 'var(--space-2)',
    }}>
      <Field label="Etnia" name="ethnicity" value={form.ethnicity} options={FACE_OPTIONS.ethnicity} onChange={onUpdate} />
      <Field label="Color de ojos" name="eye_color" value={form.eye_color} options={FACE_OPTIONS.eye_color} onChange={onUpdate} />
      <Field label="Color de pelo" name="hair_color" value={form.hair_color} options={FACE_OPTIONS.hair_color} onChange={onUpdate} />
      <Field label="Estilo de pelo" name="hair_style" value={form.hair_style} options={FACE_OPTIONS.hair_style} onChange={onUpdate} />
      <Field label="Tono de piel" name="skin_tone" value={form.skin_tone} options={FACE_OPTIONS.skin_tone} onChange={onUpdate} />
      <Field label="Rango de edad" name="age_range" value={form.age_range} options={FACE_OPTIONS.age_range} onChange={onUpdate} />
    </div>
  );
}


function Field({ label, name, value, options, onChange }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>{label}</span>
      <select value={value || ''} onChange={(e) => onChange(name, e.target.value)}>
        <option value="">(elegir)</option>
        {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
      </select>
    </label>
  );
}
