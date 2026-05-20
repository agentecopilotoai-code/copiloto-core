/**
 * UI-INFLU-009 — Wizard Paso 2: Cuerpo.
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader, Stepper } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import {
  HEIGHT_MAX_CM,
  HEIGHT_MIN_CM,
  POSTURES,
  SILHOUETTES,
  buildBodyPayload,
  silhouetteLabel,
  validateHeight,
} from './step2BodyData.js';


const STEPS = [
  { id: 'face', label: 'Cara', state: 'complete' },
  { id: 'body', label: 'Cuerpo', state: 'current' },
  { id: 'identity', label: 'Identidad', state: 'upcoming' },
  { id: 'voice', label: 'Voz', state: 'upcoming' },
  { id: 'platforms', label: 'Plataformas', state: 'upcoming' },
];


export function Step2Body({
  initialForm = {},
  bodyViews = null,
  onNext,
  onSaveDraft,
  onGenerateViews,
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
    <div data-module="influencer" data-view="wizard-step-2">
      <PageHeader eyebrow="Crear personaje · Paso 2 de 5" title="Cuerpo" />
      <Stepper steps={STEPS} />

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <fieldset>
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
                    ? '2px solid var(--color-action-primary-bg, #111)'
                    : '1px solid var(--color-border, #d1d5db)',
                  borderRadius: 'var(--radius-md, 6px)',
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
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <label style={{ display: 'block' }}>
          <span style={{ fontWeight: 600 }}>Altura: {form.height_cm} cm</span>
          <input
            type="range"
            min={HEIGHT_MIN_CM}
            max={HEIGHT_MAX_CM}
            value={form.height_cm}
            onChange={(e) => setForm((p) => ({ ...p, height_cm: Number(e.target.value) }))}
            aria-label="Altura en cm"
            style={{ width: '100%', marginTop: 'var(--space-1)' }}
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
          >
            {POSTURES.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
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
                border: '1px solid var(--color-border-subtle, #e5e7eb)',
                borderRadius: 'var(--radius-md, 6px)',
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
      </Card>

      {error && (
        <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>
      )}

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 'var(--space-4)',
      }}>
        <span>Paso 2 de 5</span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button type="button" onClick={() => onSaveDraft?.(buildBodyPayload(form))}>
            Guardar borrador
          </button>
          <button type="button" onClick={handleNext}>Siguiente paso</button>
        </div>
      </div>
    </div>
  );
}
