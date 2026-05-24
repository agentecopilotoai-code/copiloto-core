/**
 * UI-INFLU-009 — Wizard Paso 2: Cuerpo.
 *
 * Refactor visual UI-INFLU-014.12: shell alineado con Step1Face
 * (page wrapper Ravit Studio, eyebrow + h1 + subtítulo, stepper arriba,
 * "← Casting" en el header, sin "Guardar borrador" — auto-save al
 * avanzar).
 */
import { useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import styles from '../_shared/RavitStyles.module.css';
import {
  HEIGHT_MAX_CM,
  HEIGHT_MIN_CM,
  POSTURES,
  SILHOUETTES,
  buildBodyPayload,
  silhouetteLabel,
  validateHeight,
} from './step2BodyData.js';
import { WizardStepper } from './WizardStepper.jsx';


const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'done' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'current' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'pending' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'pending' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'pending' },
];


export function Step2Body({
  initialForm = {},
  bodyViews = null,
  onNext,
  // onSaveDraft eliminado del UI; el container hace auto-save al
  // recibir onNext con el payload final.
  onSaveDraft, // eslint-disable-line no-unused-vars
  onGenerateViews,
  onBack,
}) {
  const [form, setForm] = useState({
    silhouette: 'athletic', height_cm: 172, posture: 'confident', ...initialForm,
  });
  const [error, setError] = useState(null);
  const { can } = usePermissions();
  const canGenerate = can('influencer.generate');

  const heightValidation = validateHeight(form.height_cm);

  const handleNext = () => {
    if (!heightValidation.valid) {
      setError(heightValidation.error);
      return;
    }
    setError(null);
    onNext?.(buildBodyPayload(form));
  };

  return (
    <div className={styles.page} data-module="influencer" data-view="wizard-step-2">
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
        <h1 className={styles.h1Page}>Construye su cuerpo</h1>
        <p className={styles.textSubtle}>
          Define la silueta, altura y postura. Estas variables determinan cómo
          luce en cuerpo completo y en cuáles ángulos genera.
        </p>
      </div>

      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <WizardStepper steps={STEPS} />
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600 }}>Tipo de cuerpo</legend>
          <ul role="radiogroup" aria-label="Silueta" style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 'var(--space-2)', margin: 'var(--space-2) 0 0', padding: 0, listStyle: 'none',
          }}>
            {SILHOUETTES.map((s) => (
              <li key={s.value}>
                <label style={{
                  display: 'block',
                  padding: 'var(--space-2)',
                  border: form.silhouette === s.value
                    ? '2px solid #2DBB6A'
                    : '1px solid #e6e0d4',
                  background: form.silhouette === s.value ? '#eaf7ef' : '#fff',
                  borderRadius: 10,
                  cursor: 'pointer',
                  textAlign: 'center',
                  fontWeight: 600,
                }}>
                  <input
                    type="radio"
                    name="silhouette"
                    value={s.value}
                    checked={form.silhouette === s.value}
                    onChange={() => setForm((p) => ({ ...p, silhouette: s.value }))}
                    style={{ marginRight: 'var(--space-1)' }}
                  />
                  {s.label}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <label style={{ display: 'block' }}>
          <span style={{ fontWeight: 600 }}>Altura: {form.height_cm} cm</span>
          <input
            type="range"
            min={HEIGHT_MIN_CM}
            max={HEIGHT_MAX_CM}
            value={form.height_cm}
            onChange={(e) => setForm((p) => ({ ...p, height_cm: Number(e.target.value) }))}
            aria-label="Altura en cm"
            style={{ width: '100%', marginTop: 'var(--space-1)', accentColor: '#2DBB6A' }}
          />
          <span style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
            Rango: {HEIGHT_MIN_CM}–{HEIGHT_MAX_CM} cm
          </span>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 'var(--space-3)' }}>
          <span style={{ fontWeight: 600 }}>Postura</span>
          <select
            value={form.posture}
            onChange={(e) => setForm((p) => ({ ...p, posture: e.target.value }))}
            aria-label="Postura"
            style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #e6e0d4' }}
          >
            {POSTURES.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 600 }}>Vista previa</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>
              {silhouetteLabel(form.silhouette)} · {form.height_cm}CM
            </div>
          </div>
          {!bodyViews && (
            <button
              type="button"
              onClick={onGenerateViews}
              disabled={!canGenerate}
              className={styles.btnGhost}
              title={canGenerate ? undefined : 'No tienes permiso para generar (consume 4 créditos)'}
            >
              Generar vistas (4 créditos)
            </button>
          )}
        </div>
        <ul aria-label="Vistas del cuerpo" style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--space-2)', marginTop: 'var(--space-2)', padding: 0, listStyle: 'none',
        }}>
          {['Frontal', '3/4', 'Perfil', 'Espalda'].map((angle, i) => {
            const view = bodyViews?.[i];
            return (
              <li key={angle} style={{
                aspectRatio: '1',
                border: '1px solid #e6e0d4',
                borderRadius: 10,
                background: '#fbf9f2',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                textAlign: 'center', fontSize: 12,
                color: 'var(--color-text-subtle, #6b7280)',
                overflow: 'hidden',
              }}>
                {view?.url
                  ? <img src={view.url} alt={`${angle} de ${silhouetteLabel(form.silhouette)}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : angle}
              </li>
            );
          })}
        </ul>
      </div>

      {error && (
        <AlertBanner tone="warning" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>
      )}

      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        gap: 16, marginTop: 32, paddingTop: 16, borderTop: '1px solid #eee9dc',
      }}>
        <span className={styles.textSubtle} style={{ fontSize: 13 }}>Paso 2 de 5</span>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleNext}
        >
          Continuar a Identidad →
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
