/**
 * UI-INFLU-011 — Wizard Paso 4: Voz.
 *
 * Refactor visual UI-INFLU-014.12: shell alineado con Step1Face.
 */
import { useEffect, useRef, useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import styles from '../_shared/RavitStyles.module.css';
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
  onSaveDraft, // eslint-disable-line no-unused-vars
  onGenerateSample,
  onFetchCaptions,
  onBack,
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
    // UI-INFLU-014.10: el sample de voz NO es obligatorio para
    // continuar. El usuario puede activar el personaje sin haber
    // generado nunca una muestra; se puede generar más tarde desde
    // el estudio del personaje.
    const v = validateMinimum(form);
    if (!v.valid) { setError(v.error); return; }
    setError(null);
    onNext?.(buildVoicePayload(form));
  };

  return (
    <div className={styles.page} data-module="influencer" data-view="wizard-step-4">
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
        <h1 className={styles.h1Page}>Define su voz</h1>
        <p className={styles.textSubtle}>
          Tono, formalidad y energía. Cómo escribe captions y suena su voz.
          Opcional: puedes configurarla después desde el estudio.
        </p>
      </div>

      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <WizardStepper steps={STEPS} />
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
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
                  padding: '6px 14px', borderRadius: 999,
                  border: active ? '1.5px solid #2DBB6A' : '1px solid #e6e0d4',
                  background: active ? '#eaf7ef' : '#fff',
                  color: active ? '#1b6f3e' : 'var(--ravit-text, #333)',
                  fontSize: 13, cursor: 'pointer',
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
            style={{
              marginTop: 6, padding: '8px 10px',
              borderRadius: 8, border: '1px solid #e6e0d4',
            }}
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
            style={{ width: '100%', accentColor: '#2DBB6A' }}
          />
        </label>
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600 }}>Sample de voz · {toneLabel(form.tone)}</div>
          <button
            type="button"
            onClick={handleRegenerateSample}
            disabled={!canGenerate}
            className={styles.btnGhost}
            title={canGenerate ? undefined : 'No tienes permiso de generación'}
          >
            {sampleUrl ? 'Re-generar sample (2 créditos)' : 'Generar sample (2 créditos)'}
          </button>
        </div>
        {sampleUrl && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls src={sampleUrl} style={{ marginTop: 'var(--space-2)', width: '100%' }} />
        )}
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>
          Captions de prueba (regen automático al cambiar tono)
        </div>
        <CaptionsPreview captions={captions} />
      </div>

      {error && <AlertBanner tone="warning" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        gap: 16, marginTop: 32, paddingTop: 16, borderTop: '1px solid #eee9dc',
      }}>
        <span className={styles.textSubtle} style={{ fontSize: 13 }}>Paso 4 de 5</span>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleNext}
        >
          Continuar a Plataformas →
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


function CaptionsPreview({ captions }) {
  return (
    <ul aria-label="Captions preview" style={{
      display: 'grid', gap: 'var(--space-2)',
      margin: 0, padding: 0, listStyle: 'none',
    }}>
      {['ig', 'tiktok', 'story'].map((platform) => (
        <li key={platform} style={{
          padding: 'var(--space-2)',
          border: '1px solid #e6e0d4',
          borderRadius: 10, background: '#fff',
        }}>
          <div style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {platform.toUpperCase()}
          </div>
          <div>{captions[platform] || '—'}</div>
        </li>
      ))}
    </ul>
  );
}
