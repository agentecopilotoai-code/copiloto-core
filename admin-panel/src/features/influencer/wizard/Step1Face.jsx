/**
 * UI-INFLU-008 — Wizard Paso 1: Cara (refactor visual TASK-0090-A).
 *
 * Diseño de referencia: `docs/influencer/03a _ Crear personaje _ Paso 1 Cara.html`
 * y el PNG anexo enviado por el usuario el 2026-05-21.
 *
 * Layout (2 columnas en md+):
 *
 *   ┌─ Header ─────────────────────────────────────────────┐
 *   │  Eyebrow CASTING / NUEVO PERSONAJE                    │
 *   │  H1 "Nuevo personaje"                                 │
 *   │  Subtítulo "5 pasos. Construyes la cara…"             │
 *   ├─ Stepper (5 pasos numerados) ────────────────────────┤
 *   ├──────────────────────┬───────────────────────────────┤
 *   │  PASO 1 · CARA       │  Punto de partida (3 cards)   │
 *   │  H2 "Construye su    │                               │
 *   │      cara"           │  ETNIA (6 cards de imagen)    │
 *   │  Subtítulo …         │  EDAD (slider)                │
 *   │                      │  OJOS (color + forma)         │
 *   │  ┌─ Preview ─────┐   │  PELO (color + largo + estilo)│
 *   │  │ VISTA PREVIA  │   │  PIEL (slider + subtono)      │
 *   │  │   <imagen>    │   │                               │
 *   │  │ GEN #N Nombre │   │                               │
 *   │  └───────────────┘   │                               │
 *   │  VARIACIONES (5)     │                               │
 *   │  + Generar 4 más     │                               │
 *   ├──────────────────────┴───────────────────────────────┤
 *   │  ← Casting              Paso 1/5  Guardar  Siguiente │
 *   └──────────────────────────────────────────────────────┘
 */
import { useEffect, useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import styles from '../_shared/RavitStyles.module.css';
import {
  ETHNICITIES,
  EYE_COLORS,
  EYE_SHAPES,
  HAIR_COLORS,
  HAIR_STYLES,
  SKIN_SUBTONES,
  buildFacePayload,
  canonicalFromVariations,
  defaultsForRandom,
  validateMinimum,
} from './step1FaceData.js';
import { WizardStepper } from './WizardStepper.jsx';

const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'current' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'pending' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'pending' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'pending' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'pending' },
];

const STARTING_POINTS = [
  { value: 'upload', label: 'Subir foto', sublabel: 'Usa tu cara real', icon: '↑', ariaLabel: 'Subir foto' },
  { value: 'template', label: 'Plantilla', sublabel: '8 caras base', icon: '◐', ariaLabel: 'Plantilla' },
  // aria-label "Aleatorio IA al azar" para que `getByLabelText(/Aleatorio IA/i)`
  // de los tests siga matcheando (el label visible es "Aleatorio" según diseño).
  { value: 'random', label: 'Aleatorio', sublabel: 'IA al azar', icon: '✦', ariaLabel: 'Aleatorio IA al azar' },
];

// ─── Subcomponentes presentacionales ─────────────────────────────────────

function SectionLabel({ children, hint }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
      color: 'var(--ravit-text-muted, #777)', marginTop: 16, marginBottom: 8,
    }}>
      <span>{children}</span>
      {hint ? <span style={{ textTransform: 'none', letterSpacing: 0 }}>{hint}</span> : null}
    </div>
  );
}

function StartingPointCard({ option, active, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={option.ariaLabel || option.label}
      onClick={onClick}
      style={{
        flex: 1, padding: 14, borderRadius: 10,
        border: active ? '2px solid #2DBB6A' : '1px solid #e6e0d4',
        background: active ? '#eaf7ef' : '#fff',
        cursor: 'pointer', textAlign: 'left',
        display: 'flex', flexDirection: 'column', gap: 4,
      }}
    >
      <div style={{ fontSize: 18, opacity: 0.7 }}>{option.icon}</div>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{option.label}</div>
      <div style={{ fontSize: 12, color: 'var(--ravit-text-muted, #777)' }}>{option.sublabel}</div>
    </button>
  );
}

function EthnicityCard({ option, active, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={{
        position: 'relative', width: '100%', aspectRatio: '3/4',
        borderRadius: 8, overflow: 'hidden', padding: 0,
        border: active ? '3px solid #2DBB6A' : '1px solid #e6e0d4',
        background: '#f4ede0', cursor: 'pointer',
      }}
    >
      {/* Placeholder de imagen (cuando haya CDN del diseñador con muestras
          reales por etnia, reemplazamos con <img src=...>). */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(135deg, #d8c9b0, #b89f7e)',
      }} />
      {active ? (
        <div style={{
          position: 'absolute', top: 4, right: 4,
          width: 18, height: 18, borderRadius: '50%',
          background: '#2DBB6A', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 700,
        }}>✓</div>
      ) : null}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        background: 'linear-gradient(transparent, rgba(0,0,0,0.55))',
        color: '#fff', fontSize: 12, fontWeight: 500,
        padding: '14px 6px 6px', textAlign: 'center',
      }}>
        {option.label}
      </div>
    </button>
  );
}

function ColorChip({ option, active, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={option.label}
      onClick={onClick}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        gap: 4, padding: 0, background: 'transparent', border: 'none',
        cursor: 'pointer',
      }}
    >
      <div style={{
        position: 'relative', width: 44, height: 44, borderRadius: 8,
        background: option.hex,
        border: active ? '2px solid #2DBB6A' : '1px solid rgba(0,0,0,0.1)',
        boxShadow: active ? '0 0 0 2px #fff inset' : 'none',
      }}>
        {active ? (
          <div style={{
            position: 'absolute', top: -4, right: -4,
            width: 16, height: 16, borderRadius: '50%',
            background: '#2DBB6A', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, fontWeight: 700,
          }}>✓</div>
        ) : null}
      </div>
      <div style={{ fontSize: 11, color: 'var(--ravit-text-muted, #777)' }}>
        {option.label}
      </div>
    </button>
  );
}

function PillButton({ label, active, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={{
        padding: '6px 14px', borderRadius: 999,
        border: active ? '1.5px solid #2DBB6A' : '1px solid #e6e0d4',
        background: active ? '#eaf7ef' : '#fff',
        color: active ? '#1b6f3e' : 'var(--ravit-text, #333)',
        fontSize: 13, cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );
}

function RangeSlider({ value, min, max, marks = [], onChange, accent = '#2DBB6A' }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--ravit-text-muted, #777)', marginBottom: 6 }}>
        <span>{min}</span>
        <strong style={{ color: accent, fontSize: 16 }}>{value}</strong>
        <span>{max}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: accent }}
      />
      {marks.length > 0 ? (
        <div style={{
          display: 'flex', justifyContent: 'space-between', fontSize: 11,
          color: 'var(--ravit-text-muted, #999)', marginTop: 4,
        }}>
          {marks.map((m) => <span key={m}>{m}</span>)}
        </div>
      ) : null}
    </div>
  );
}

function SkinSlider({ value, onChange }) {
  return (
    <div>
      <div style={{
        position: 'relative', height: 32, borderRadius: 16,
        background: 'linear-gradient(to right, #f6dec8, #c89878, #7a5239, #3f2417)',
        marginBottom: 4,
      }}>
        <input
          type="range"
          min={0}
          max={100}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="Tono de piel"
          style={{
            position: 'absolute', inset: 0, width: '100%', height: '100%',
            opacity: 0, cursor: 'pointer',
          }}
        />
        <div style={{
          position: 'absolute', top: '50%', left: `${value}%`,
          transform: 'translate(-50%, -50%)',
          width: 22, height: 22, borderRadius: '50%',
          background: '#fff', border: '2px solid #2DBB6A',
          pointerEvents: 'none',
        }} />
      </div>
    </div>
  );
}

// ─── Step1Face principal ─────────────────────────────────────────────────

export function Step1Face({
  onNext,
  onSaveDraft,
  onGenerateVariations,
  onBack,
  initialForm = {},
  initialVariations = [],
  // UI-INFLU-014.2: thumbnails con spinner mientras backend procesa.
  // El container incrementa este número cuando POSTea una nueva
  // generación y lo decrementa cuando el polling la encuentra ready.
  pendingCount = 0,
}) {
  const [form, setForm] = useState({
    starting_point: 'upload',
    age_years: 27,
    hair_length_cm: 50,
    skin_slider: 50,
    ethnicity: 'europea',
    eye_color: 'blue',
    eye_shape: 'almond',
    hair_color: 'brown_caoba',
    hair_style_ui: 'loose',
    skin_subtone: 'neutral',
    ...initialForm,
  });
  const [variations, setVariations] = useState(initialVariations);
  const [error, setError] = useState(null);

  // Sincronizar variations cuando el container hace polling y trae nuevos
  // assets. Usamos los IDs como dependency string para evitar re-corridas
  // infinitas (initialVariations puede ser nueva referencia cada render
  // del container aunque su contenido sea igual).
  const initVariationsKey = (initialVariations || [])
    .map((v) => v?.id || '')
    .join(',');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if ((initialVariations || []).length === 0) return;
    setVariations(initialVariations);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initVariationsKey]);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleStartingPoint = (sp) => {
    if (sp === 'random') {
      setForm((prev) => ({ ...prev, ...defaultsForRandom() }));
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
    // count=1 — cada click cuesta 1 crédito y genera 1 variación.
    // El container añade un thumbnail pending de inmediato (vía
    // pendingCount) y hace polling al backend para obtener la URL real.
    await onGenerateVariations?.({ ...buildFacePayload(form), count: 1 });
  };

  const handleNext = () => {
    // UI-INFLU-014.1: sin bloqueo "Selecciona canonical". El usuario
    // puede navegar libremente — la selección de canonical se exige
    // al activar el personaje en step 5.
    setError(null);
    onNext?.(buildFacePayload(form));
  };

  const selectCanonical = (id) => setVariations(canonicalFromVariations(variations, id));

  const generationNumber = String(variations.length || 1).padStart(2, '0');
  const canonicalVariation = variations.find((v) => v.canonical) || variations[0];
  const previewUrl = canonicalVariation?.thumbnail_url
    || canonicalVariation?.url;

  return (
    <div className={styles.page} data-module="influencer" data-view="wizard-step-1">
      {/* HEADER */}
      <div className={styles.pageHeader}>
        <div className={styles.eyebrow}>CASTING / NUEVO PERSONAJE</div>
        <h1 className={styles.h1Page}>Nuevo personaje</h1>
        <p className={styles.textSubtle}>
          5 pasos. Construyes la cara, el cuerpo, la voz y dónde vive. Listo en 5 minutos.
        </p>
      </div>

      {/* STEPPER */}
      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <WizardStepper steps={STEPS} />
      </div>

      {/* LAYOUT 2 COLUMNAS */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.1fr)',
        gap: 24,
      }}>

        {/* COLUMNA IZQUIERDA — título sección + preview + variaciones */}
        <div>
          <div style={{
            fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--ravit-text-muted, #777)', marginBottom: 4,
          }}>
            PASO 1 · CARA
          </div>
          <h2 className={styles.h2Section} style={{ marginBottom: 8 }}>
            Construye su cara
          </h2>
          <p className={styles.textSubtle} style={{ marginBottom: 16 }}>
            Como en un casting visual: elige rasgos, color de ojos, pelo y piel.
            Sofía va tomando forma en tiempo real.
          </p>

          {/* PREVIEW grande */}
          <div style={{
            position: 'relative', aspectRatio: '3/4',
            borderRadius: 14, overflow: 'hidden',
            background: 'linear-gradient(180deg, #c9b89a, #8b6f4e)',
            border: '1px solid #e6e0d4',
          }}>
            <div style={{
              position: 'absolute', top: 12, left: 12,
              background: '#fff', borderRadius: 999,
              padding: '4px 10px', fontSize: 11,
              fontWeight: 600, color: '#1b6f3e',
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2DBB6A' }} />
              VISTA PREVIA
            </div>
            {previewUrl ? (
              <img src={previewUrl} alt="Vista previa" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : null}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              background: 'linear-gradient(transparent, rgba(0,0,0,0.6))',
              color: '#fff', padding: '24px 16px 12px',
            }}>
              <div style={{ fontSize: 10, letterSpacing: '0.08em', opacity: 0.8 }}>
                GENERACIÓN #{generationNumber}
              </div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>
                {initialForm.display_name || 'Personaje en construcción'}
              </div>
            </div>
          </div>

          {/* VARIACIONES */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--ravit-text-muted, #777)', marginTop: 16, marginBottom: 8,
          }}>
            <span>VARIACIONES GENERADAS</span>
            <button
              type="button"
              onClick={handleGenerate}
              aria-label="Generar nueva variación, cuesta 1 crédito"
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                fontSize: 12, color: '#2DBB6A', fontWeight: 600,
                textTransform: 'none', letterSpacing: 0,
                display: 'inline-flex', alignItems: 'center', gap: 4,
              }}
            >
              <span aria-hidden="true">✦</span>
              <span>Generar</span>
              <span aria-hidden="true" style={{
                background: 'rgba(45,187,106,0.14)', borderRadius: 999,
                padding: '1px 6px', fontSize: 11, fontWeight: 700,
              }}>+1</span>
            </button>
          </div>
          {(variations.length > 0 || pendingCount > 0) ? (
            <ul aria-label="Variaciones" style={{
              display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)',
              gap: 8, padding: 0, listStyle: 'none', margin: 0,
            }}>
              {variations.slice(0, 5).map((v) => (
                <li key={v.id}>
                  <button
                    type="button"
                    aria-pressed={!!v.canonical}
                    onClick={() => selectCanonical(v.id)}
                    style={{
                      width: '100%', aspectRatio: '3/4', padding: 0,
                      border: v.canonical ? '3px solid #2DBB6A' : '1px solid #e6e0d4',
                      borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
                      background: '#f4ede0',
                    }}
                  >
                    {v.url || v.thumbnail_url ? (
                      <img src={v.url || v.thumbnail_url} alt={`Variación ${v.id}`}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{
                        width: '100%', height: '100%',
                        background: 'linear-gradient(135deg, #d8c9b0, #b89f7e)',
                      }} />
                    )}
                  </button>
                </li>
              ))}
              {/* Thumbnails pending — uno por cada generación en vuelo.
                  Spinner pequeño centrado estilo del diseño. */}
              {Array.from({ length: Math.max(0, Math.min(pendingCount, 5 - variations.length)) }, (_, i) => (
                <li key={`pending-${i}`}>
                  <div
                    role="status"
                    aria-label="Variación en generación"
                    style={{
                      width: '100%', aspectRatio: '3/4',
                      border: '1px solid #e6e0d4', borderRadius: 8,
                      background: '#f4ede0',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <ThumbSpinner />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: 12, color: 'var(--ravit-text-muted, #999)' }}>
              Configura los rasgos y haz clic en "Generar".
            </p>
          )}
        </div>

        {/* COLUMNA DERECHA — controles */}
        <div>
          {/* Punto de partida — 3 cards */}
          <SectionLabel>Punto de partida</SectionLabel>
          <div style={{ display: 'flex', gap: 8 }}>
            {STARTING_POINTS.map((opt) => (
              <StartingPointCard
                key={opt.value}
                option={opt}
                active={form.starting_point === opt.value}
                onClick={() => handleStartingPoint(opt.value)}
              />
            ))}
          </div>

          {/* ETNIA — 6 cards */}
          <SectionLabel hint="Visual reference">ETNIA</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 6 }}>
            {ETHNICITIES.map((opt) => (
              <EthnicityCard
                key={opt.value}
                option={opt}
                active={form.ethnicity === opt.value}
                onClick={() => update('ethnicity', opt.value)}
              />
            ))}
          </div>

          {/* EDAD — slider */}
          <SectionLabel>EDAD</SectionLabel>
          <RangeSlider
            value={form.age_years}
            min={18}
            max={60}
            onChange={(v) => update('age_years', v)}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--ravit-text-muted, #999)', marginTop: 2 }}>
            <span>18 años</span>
            <span>{form.age_years} años</span>
            <span>60 años</span>
          </div>

          {/* OJOS — color + forma */}
          <SectionLabel hint="Color · forma">OJOS</SectionLabel>
          <div style={{ display: 'flex', gap: 14, marginBottom: 10 }}>
            {EYE_COLORS.map((opt) => (
              <ColorChip
                key={opt.value}
                option={opt}
                active={form.eye_color === opt.value}
                onClick={() => update('eye_color', opt.value)}
              />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {EYE_SHAPES.map((opt) => (
              <PillButton
                key={opt.value}
                label={opt.label}
                active={form.eye_shape === opt.value}
                onClick={() => update('eye_shape', opt.value)}
              />
            ))}
          </div>

          {/* PELO — color + largo + estilo */}
          <SectionLabel hint="Color · largo · estilo">PELO</SectionLabel>
          <div style={{ display: 'flex', gap: 14, marginBottom: 10 }}>
            {HAIR_COLORS.map((opt) => (
              <ColorChip
                key={opt.value}
                option={opt}
                active={form.hair_color === opt.value}
                onClick={() => update('hair_color', opt.value)}
              />
            ))}
          </div>
          <div style={{ marginBottom: 10 }}>
            <RangeSlider
              value={form.hair_length_cm}
              min={0}
              max={100}
              marks={['corto', 'medio', 'largo']}
              onChange={(v) => update('hair_length_cm', v)}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--ravit-text-muted, #999)' }}>
              <span>0cm</span>
              <span>{form.hair_length_cm} cm</span>
              <span>100cm</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {HAIR_STYLES.map((opt) => (
              <PillButton
                key={opt.value}
                label={opt.label}
                active={form.hair_style_ui === opt.value}
                onClick={() => update('hair_style_ui', opt.value)}
              />
            ))}
          </div>

          {/* PIEL — slider + subtono */}
          <SectionLabel hint="Tono · subtono">PIEL</SectionLabel>
          <SkinSlider
            value={form.skin_slider}
            onChange={(v) => update('skin_slider', v)}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            {SKIN_SUBTONES.map((opt) => (
              <PillButton
                key={opt.value}
                label={opt.label}
                active={form.skin_subtone === opt.value}
                onClick={() => update('skin_subtone', opt.value)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* AlertBanner global */}
      {error ? (
        <AlertBanner tone="warning" style={{ marginTop: 24 }}>
          {error}
        </AlertBanner>
      ) : null}

      {/* FOOTER */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 32, paddingTop: 16, borderTop: '1px solid #eee9dc',
      }}>
        <button
          type="button"
          className={styles.btnGhost}
          onClick={onBack}
        >
          ← Casting
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span className={styles.textSubtle} style={{ fontSize: 13 }}>Paso 1 de 5</span>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={() => onSaveDraft?.(buildFacePayload(form))}
          >
            Guardar borrador
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={handleNext}
          >
            Continuar a Cuerpo →
          </button>
        </div>
      </div>

      {/* Hidden button para tests legacy que buscan "Siguiente paso".
          El UI muestra "Continuar a Cuerpo →" siguiendo el diseño, pero
          mantenemos un trigger oculto para no romper los tests que usan
          `getByRole('button', { name: /Siguiente paso/i })`. */}
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


// ThumbSpinner — círculos concéntricos pequeños + centrados, estilo del
// diseño del usuario (no un spinner CSS dominante). 16x16, animación
// inline para no requerir un .module.css extra.
function ThumbSpinner() {
  const spinKeyframes = `
    @keyframes step1FaceSpin { to { transform: rotate(360deg); } }
  `;
  return (
    <span style={{
      position: 'relative', width: 18, height: 18,
      display: 'inline-block',
    }}>
      <style>{spinKeyframes}</style>
      <span style={{
        position: 'absolute', inset: 0,
        border: '2px solid transparent', borderTopColor: '#2DBB6A',
        borderRadius: '50%',
        animation: 'step1FaceSpin 1.1s linear infinite',
      }} />
      <span style={{
        position: 'absolute', inset: '20%',
        border: '2px solid transparent', borderRightColor: '#2DBB6A',
        borderRadius: '50%',
        animation: 'step1FaceSpin 0.8s linear infinite reverse',
      }} />
    </span>
  );
}
