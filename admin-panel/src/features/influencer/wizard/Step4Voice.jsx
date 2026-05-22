/**
 * UI-INFLU-011 — Wizard Paso 4: Voz.
 */
import { useEffect, useRef, useState } from 'react';

import { AlertBanner, Card, PageHeader } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import {
  FORMALITIES,
  TONES,
  buildVoicePayload,
  captionPromptHash,
  toneLabel,
  validateMinimum,
} from './step4VoiceData.js';
import { WizardStepper } from './WizardStepper.jsx';


const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'done' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'done' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'done' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'current' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'pending' },
];


export function Step4Voice({
  initialForm = {},
  sampleUrl: initialSampleUrl = null,
  onNext,
  onSaveDraft,
  onGenerateSample,
  onFetchCaptions,
}) {
  const [form, setForm] = useState({
    tone: 'warm', formality: 'neutral', energy_level: 5, ...initialForm,
  });
  const [sampleUrl, setSampleUrl] = useState(initialSampleUrl);
  const [captions, setCaptions] = useState({ ig: '', tiktok: '', story: '' });
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const { can } = usePermissions();
  const canGenerate = can('influencer.generate');

  const update = (key, value) => setForm((p) => ({ ...p, [key]: value }));

  // Debounce: cada cambio de tono/formality/energy → 1s → fetchCaptions.
  useEffect(() => {
    if (!onFetchCaptions) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const hash = captionPromptHash(form);
    debounceRef.current = setTimeout(() => {
      onFetchCaptions(buildVoicePayload(form), hash).then((data) => {
        if (data?.captions) setCaptions(data.captions);
      });
    }, 1000);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [form.tone, form.formality, form.energy_level, onFetchCaptions]);

  const handleRegenerateSample = async () => {
    if (!onGenerateSample) return;
    const result = await onGenerateSample(buildVoicePayload(form));
    if (result?.audio_url) setSampleUrl(result.audio_url);
  };

  const handleNext = () => {
    const v = validateMinimum(form);
    if (!v.valid) { setError(v.error); return; }
    if (!sampleUrl) {
      setError('Genera al menos un sample de voz antes de continuar.');
      return;
    }
    setError(null);
    onNext?.(buildVoicePayload(form));
  };

  return (
    <div data-module="influencer" data-view="wizard-step-4">
      <PageHeader eyebrow="Crear personaje · Paso 4 de 5" title="Voz" />
      <WizardStepper steps={STEPS} />

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600 }}>Tono</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', marginTop: 'var(--space-1)' }}>
          {TONES.map((t) => {
            const active = form.tone === t.value;
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => update('tone', t.value)}
                aria-pressed={active}
                style={{
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: active ? 'var(--color-action-primary-bg, #111)' : 'transparent',
                  color: active ? 'var(--color-action-primary-fg, #fff)' : 'inherit',
                  border: '1px solid var(--color-border, #d1d5db)',
                  cursor: 'pointer',
                }}
              >{t.label}</button>
            );
          })}
        </div>

        <div style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontWeight: 600 }}>Formalidad</div>
          <select
            value={form.formality}
            onChange={(e) => update('formality', e.target.value)}
            aria-label="Formalidad"
          >
            {FORMALITIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </div>

        <label style={{ display: 'block', marginTop: 'var(--space-3)' }}>
          <span style={{ fontWeight: 600 }}>Energía: {form.energy_level}/10 (calmada ↔ enérgica)</span>
          <input
            type="range" min="1" max="10"
            value={form.energy_level}
            onChange={(e) => update('energy_level', Number(e.target.value))}
            aria-label="Nivel de energía"
            style={{ width: '100%' }}
          />
        </label>
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600 }}>Sample de voz · {toneLabel(form.tone)}</div>
          <button
            type="button"
            onClick={handleRegenerateSample}
            disabled={!canGenerate}
            title={canGenerate ? undefined : 'No tienes permiso de generación'}
          >
            {sampleUrl ? 'Re-generar sample (2 créditos)' : 'Generar sample (2 créditos)'}
          </button>
        </div>
        {sampleUrl && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls src={sampleUrl} style={{ marginTop: 'var(--space-2)', width: '100%' }} />
        )}
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>
          Captions de prueba (regen automático al cambiar tono)
        </div>
        <CaptionsPreview captions={captions} />
      </Card>

      {error && <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 'var(--space-4)',
      }}>
        <span>Paso 4 de 5</span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button type="button" onClick={() => onSaveDraft?.(buildVoicePayload(form))}>
            Guardar borrador
          </button>
          <button type="button" onClick={handleNext}>Siguiente paso</button>
        </div>
      </div>
    </div>
  );
}


function CaptionsPreview({ captions }) {
  return (
    <ul aria-label="Captions preview" style={{
      display: 'grid', gap: 'var(--space-2)',
      margin: 0, padding: 0, listStyle: 'none',
    }}>
      {['ig', 'tiktok', 'story'].map((platform) => (
        <li key={platform} style={{
          padding: 'var(--space-2)',
          border: '1px solid var(--color-border-subtle, #e5e7eb)',
          borderRadius: 'var(--radius-md, 6px)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
            {platform.toUpperCase()}
          </div>
          <div>{captions[platform] || '—'}</div>
        </li>
      ))}
    </ul>
  );
}
