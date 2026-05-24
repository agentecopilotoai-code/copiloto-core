/**
 * UI-INFLU-005 — Estudio del personaje (redesign UI-INFLU-014.13).
 *
 * Vista "Estudio · generar" — orientada a la acción principal: generar
 * contenido en nombre del personaje activo. Estructura:
 *
 *   ┌─ Eyebrow: NOMBRE / ESTUDIO ──────────────────────────────────────┐
 *   │  H1 "Estudio · generar"                                          │
 *   │  Subtítulo                                                       │
 *   ├─ Persona switcher (pill con avatar + nombre + variaciones + +) ──┤
 *   ├─ "¿Qué quieres crear hoy?" + 5 cards de formato ─────────────────┤
 *   ├─ COMPOSER · "Describe la escena" + textarea + acciones ──────────┤
 *   ├─ ÚLTIMA GENERACIÓN + grid de generaciones recientes ─────────────┤
 *   │                                                                  │
 *   │  COLUMNA DERECHA (sticky):                                       │
 *   │  - Ajustes (formato 1:1/4:5/9:16/16:9, cantidad slider,          │
 *   │    estilo visual, locación opcional, modo seguro)                │
 *   │  - CTA grande "Generar · N imágenes"                             │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Reutiliza la paleta y los helpers de `_shared/RavitStyles.module.css`
 * para consistencia con Step1Face y el wizard.
 */
import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { usePermissions } from '../../../permissions/index.js';
import shared from '../_shared/RavitStyles.module.css';
import {
  KINDS,
  PROMPT_MAX,
  buildGeneratePayload,
  computeCost,
  formatsForKind,
  kindMeta,
  promptWithinLimit,
} from '../generate/generateData.js';
import {
  formatScheduledCount,
  statusLabel,
  tagsFromVoice,
} from './personaStudioData.js';


// Tipos que producen video — el thumbnail debe ser <video> no <img>.
const VIDEO_KINDS = new Set(['reel', 'story']);


function isVideoAsset(asset, fallbackKind) {
  const mime = asset?.mime || '';
  if (mime.startsWith('video/')) return true;
  if (asset?.duration_s != null) return true;
  if (fallbackKind && VIDEO_KINDS.has(fallbackKind)) return true;
  return false;
}


const STYLE_PRESETS = [
  { value: 'editorial_warm', label: 'Editorial · cálido' },
  { value: 'editorial_cool', label: 'Editorial · frío' },
  { value: 'street_natural', label: 'Street · natural' },
  { value: 'studio_clean', label: 'Studio · clean' },
  { value: 'cinematic', label: 'Cinematic' },
];


const KIND_ICONS = {
  photo: '🖼',
  reel: '▶',
  carousel: '▤',
  story: '◐',
  ad: '◉',
};


const KIND_SUBLABEL = {
  photo: '1 imagen',
  reel: '15–60s vertical',
  carousel: 'Hasta 10 imágenes',
  story: '24h vertical',
  ad: 'Meta + copy',
};


export function PersonaStudio({
  studio,
  loading = false,
  error = null,
  balance = null,  // null → no se muestra warning de balance
  onGenerate,
  onSchedulePost,
  onUploadReference,  // (file: File) => Promise<{ url: string }>
}) {
  const navigate = useNavigate();
  const { tenantSlug, personaId } = useParams();
  const { can } = usePermissions();
  const canGenerate = can('influencer.generate');

  const [form, setForm] = useState({
    kind: 'photo',
    prompt: '',
    format: '1:1',
    count: 4,
    style: STYLE_PRESETS[0].value,
    location: '',
    reference_image_url: '',
    safety_mode: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [generationError, setGenerationError] = useState(null);
  const [uploadingReference, setUploadingReference] = useState(false);
  const fileInputRef = useRef(null);

  if (loading) {
    return (
      <div className={shared.page} data-module="influencer" data-view="studio">
        <p role="status" aria-live="polite">Cargando estudio…</p>
      </div>
    );
  }
  if (error || !studio?.persona) {
    return (
      <div className={shared.page} data-module="influencer" data-view="studio">
        <div className={shared.pageHeader}>
          <div className={shared.eyebrow}>Ravit Studio · Estudio</div>
          <h1 className={shared.h1Page}>Personaje no disponible</h1>
          <p className={shared.textSubtle}>
            Es posible que haya sido archivado o que no tengas acceso.
          </p>
        </div>
        <button
          type="button"
          className={shared.btnGhost}
          onClick={() => navigate(`/t/${tenantSlug}/influencer/influencer-casting`)}
        >
          ← Casting
        </button>
      </div>
    );
  }

  const { persona, stats, recent_generations: recentGenerations = [] } = studio;
  const variations = studio?.face_variations || persona?.face_variations || [];
  const avatarUrl = persona?.avatar_url
    || variations.find((v) => v.canonical)?.thumbnail_url
    || variations[0]?.thumbnail_url
    || null;

  const update = (key, value) => setForm((p) => ({ ...p, [key]: value }));
  const setKind = (kind) => {
    const validFormat = formatsForKind(kind)[0];
    setForm((p) => ({ ...p, kind, format: validFormat || '1:1' }));
  };

  const totalCost = computeCost(form.kind, form.count);
  const balanceKnown = balance !== null && balance !== undefined;
  const overBudget = balanceKnown ? totalCost > Number(balance) : false;
  const costPerAsset = kindMeta(form.kind)?.cost ?? 0;

  const handleGenerate = async () => {
    if (!canGenerate) {
      setGenerationError('No tienes permiso para generar contenido.');
      return;
    }
    if (overBudget) {
      setGenerationError(`Balance insuficiente — necesitas ${totalCost - Number(balance)} créditos más.`);
      return;
    }
    if (!promptWithinLimit(form.prompt)) {
      setGenerationError(`El prompt excede ${PROMPT_MAX} caracteres.`);
      return;
    }
    setGenerationError(null);
    setSubmitting(true);
    try {
      await onGenerate?.(buildGeneratePayload(form));
    } catch (err) {
      setGenerationError(err?.message || 'No se pudo iniciar la generación');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReferenceUpload = async (file) => {
    if (!file) return;
    if (!onUploadReference) {
      setGenerationError('Upload de referencia no disponible en este contexto.');
      return;
    }
    setUploadingReference(true);
    setGenerationError(null);
    try {
      const result = await onUploadReference(file);
      if (result?.url) {
        update('reference_image_url', result.url);
      } else {
        setGenerationError('El servidor no devolvió URL de la referencia.');
      }
    } catch (err) {
      setGenerationError(err?.message || 'No se pudo subir la foto de referencia.');
    } finally {
      setUploadingReference(false);
    }
  };

  const triggerReferencePicker = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const goCasting = () => navigate(`/t/${tenantSlug}/influencer/influencer-casting`);
  const goEditPersona = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/wizard/step-1`);
  const goFeed = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/feed`);
  const goLegacyGenerate = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/generate`);

  const personaCategory = (persona?.categories?.[0]) || tagsFromVoice(persona?.voice || {})[0] || 'Lifestyle';

  return (
    <div className={shared.page} data-module="influencer" data-view="studio">
      {/* Botón volver al casting */}
      <div style={{ marginBottom: 12 }}>
        <button
          type="button"
          onClick={goCasting}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--ravit-text-muted, #6b7280)', fontSize: 13,
            padding: '4px 0',
          }}
        >
          ← Casting
        </button>
      </div>

      {/* HEADER */}
      <div className={shared.pageHeader}>
        <div className={shared.eyebrow}>{persona.name?.toUpperCase()} / ESTUDIO</div>
        <h1 className={shared.h1Page}>Estudio · generar</h1>
        <p className={shared.textSubtle}>
          Elige formato, describe la escena, ajusta y genera. {persona.name} es la cara automática.
        </p>
      </div>

      {/* LAYOUT 2 COLUMNAS */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(280px, 360px)',
        gap: 24, alignItems: 'start',
      }}>

        {/* ─── COLUMNA PRINCIPAL ─────────────────────────────────── */}
        <div>
          {/* Persona switcher pill */}
          <PersonaSwitcher
            persona={persona}
            avatarUrl={avatarUrl}
            variations={variations}
            category={personaCategory}
            onEdit={goEditPersona}
            scheduledLabel={formatScheduledCount(persona.status, stats?.scheduled_count)}
          />

          {/* "¿Qué quieres crear hoy?" */}
          <div style={{ marginTop: 28 }}>
            <h2 className={shared.h2Section} style={{ margin: 0 }}>¿Qué quieres crear hoy?</h2>
            <p className={shared.textSubtle} style={{ marginTop: 4 }}>
              Elige un formato. La cara, voz y estilo de {persona.name} se aplican automáticamente.
            </p>
          </div>

          {/* Format cards (5) */}
          <ul aria-label="Tipo de contenido" style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 12, padding: 0, margin: '16px 0 0', listStyle: 'none',
          }}>
            {KINDS.map((k) => (
              <li key={k.value}>
                <FormatCard
                  kind={k}
                  active={form.kind === k.value}
                  onClick={() => setKind(k.value)}
                />
              </li>
            ))}
          </ul>

          {/* COMPOSER */}
          <div style={{ marginTop: 32 }}>
            <div className={shared.eyebrow}>COMPOSER</div>
            <h3 className={shared.h2Section} style={{ fontSize: 18, margin: '4px 0 12px' }}>
              Describe la escena
            </h3>
            <div className={shared.card} style={{ padding: 16 }}>
              <textarea
                value={form.prompt}
                onChange={(e) => update('prompt', e.target.value.slice(0, PROMPT_MAX))}
                aria-label="Prompt"
                placeholder={`${persona.name} en una terraza al atardecer en Tulum, vestida con lino crema y un kimono dorado…`}
                rows={5}
                style={{
                  width: '100%', resize: 'vertical',
                  border: 'none', outline: 'none',
                  fontFamily: 'inherit', fontSize: 14, lineHeight: 1.5,
                  background: 'transparent', color: 'inherit',
                }}
              />
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                marginTop: 12, paddingTop: 12, borderTop: '1px solid #eee9dc',
                flexWrap: 'wrap',
              }}>
                <ComposerActionButton icon="↑" label="Referencia" />
                <ComposerActionButton icon="▢" label="Producto" />
                <ComposerActionButton icon="✦" label="Plantilla" />
                <span style={{
                  marginLeft: 'auto', fontSize: 12,
                  color: 'var(--ravit-text-muted, #777)',
                }}>
                  {form.prompt.length} / {PROMPT_MAX}
                </span>
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={!canGenerate || submitting || overBudget}
                  className={shared.btnPrimary}
                  title={
                    !canGenerate ? 'No tienes permiso para generar' :
                    overBudget ? 'Balance insuficiente' :
                    undefined
                  }
                >
                  <span aria-hidden="true">✦</span>
                  <span>Generar · {totalCost} créditos</span>
                </button>
              </div>
            </div>
            {generationError ? (
              <p role="alert" style={{
                marginTop: 8, color: '#b91c1c', fontSize: 13,
              }}>
                {generationError}
              </p>
            ) : null}
          </div>

          {/* ÚLTIMA GENERACIÓN */}
          {recentGenerations.length > 0 ? (
            <div style={{ marginTop: 32 }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, marginBottom: 12 }}>
                <div>
                  <div className={shared.eyebrow}>ÚLTIMA GENERACIÓN</div>
                  <h3 style={{ margin: '4px 0 0', fontSize: 18, fontWeight: 700 }}>
                    {kindMeta(recentGenerations[0]?.kind)?.label || 'Generación'} · hace pocos minutos
                  </h3>
                </div>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    className={shared.btnGhost}
                    onClick={() => {
                      // Descarga simple: triggers cada item con un timeout
                      // entre cada descarga (evita que el navegador bloquee).
                      recentGenerations.forEach((g, i) => {
                        const url = g.assets?.[0]?.url || g.url;
                        if (!url) return;
                        setTimeout(() => {
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${persona.name}-${g.kind}-${i + 1}`;
                          a.click();
                        }, i * 250);
                      });
                    }}
                    style={{ padding: '6px 12px', fontSize: 13 }}
                  >
                    ↓ Descargar todas
                  </button>
                  <button
                    type="button"
                    className={shared.btnGhost}
                    onClick={() => recentGenerations[0] && onSchedulePost?.(recentGenerations[0].id || recentGenerations[0])}
                    style={{ padding: '6px 12px', fontSize: 13 }}
                  >
                    Programar post
                  </button>
                </div>
              </div>
              <ul aria-label="Últimas generaciones" style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                gap: 12, padding: 0, margin: 0, listStyle: 'none',
              }}>
                {recentGenerations.slice(0, 8).map((g, i) => (
                  <li key={g.id || i}>
                    <GenerationThumb gen={g} index={i + 1} total={Math.min(recentGenerations.length, 8)} />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Stats compactos al final (KPIs visibles para Manager) */}
          {stats ? <CompactKpis stats={stats} /> : null}

          {/* CTAs legacy (mantienen tests existentes) */}
          <div style={{ marginTop: 24, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {can('influencer.personas.write') && (
              <button type="button" onClick={goEditPersona} className={shared.btnGhost} style={{ padding: '8px 14px', fontSize: 13 }}>
                Editar cara
              </button>
            )}
            {canGenerate && (
              <button type="button" onClick={goLegacyGenerate} className={shared.btnGhost} style={{ padding: '8px 14px', fontSize: 13 }}>
                Generar contenido
              </button>
            )}
            <button type="button" onClick={goFeed} className={shared.btnGhost} style={{ padding: '8px 14px', fontSize: 13 }}>
              Ver feed
            </button>
          </div>
        </div>

        {/* ─── COLUMNA DERECHA (sticky settings) ────────────────── */}
        <aside aria-label="Ajustes de generación" style={{ position: 'sticky', top: 16 }}>
          <div className={shared.card}>
            <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700 }}>Ajustes</h3>
            <div style={{ fontSize: 12, color: 'var(--ravit-text-muted, #777)', marginBottom: 16 }}>
              {kindMeta(form.kind)?.label} · PhotoShoot AI
            </div>

            {/* Formato */}
            <SectionLabel>FORMATO</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
              {formatsForKind(form.kind).map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => update('format', fmt)}
                  aria-pressed={form.format === fmt}
                  style={{
                    padding: '8px 4px', borderRadius: 8,
                    border: form.format === fmt ? '1.5px solid #2DBB6A' : '1px solid #e6e0d4',
                    background: form.format === fmt ? '#eaf7ef' : '#fff',
                    color: form.format === fmt ? '#1b6f3e' : 'inherit',
                    fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  {fmt}
                </button>
              ))}
            </div>

            {/* Cantidad */}
            <SectionLabel style={{ marginTop: 16 }}>
              <span>CANTIDAD</span>
              <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 600, color: '#0F7A3F' }}>
                {form.count} {form.count === 1 ? 'imagen' : 'imágenes'}
              </span>
            </SectionLabel>
            <input
              type="range" min="1" max="10"
              value={form.count}
              onChange={(e) => update('count', Number(e.target.value))}
              aria-label="Cantidad"
              style={{ width: '100%', accentColor: '#2DBB6A' }}
            />
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              fontSize: 11, color: 'var(--ravit-text-muted, #999)',
            }}>
              <span>1</span><span>10</span>
            </div>

            {/* Estilo visual */}
            <SectionLabel style={{ marginTop: 16 }}>ESTILO VISUAL</SectionLabel>
            <select
              value={form.style}
              onChange={(e) => update('style', e.target.value)}
              aria-label="Estilo visual"
              style={{
                width: '100%', padding: '8px 10px',
                borderRadius: 8, border: '1px solid #e6e0d4',
                fontSize: 13, background: '#fff',
              }}
            >
              {STYLE_PRESETS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>

            {/* Locación (opcional) */}
            <SectionLabel style={{ marginTop: 16 }}>
              <span>LOCACIÓN</span>
              <span style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--ravit-text-muted, #999)' }}>
                opcional
              </span>
            </SectionLabel>
            {form.reference_image_url ? (
              <div style={{
                position: 'relative', borderRadius: 12, overflow: 'hidden',
                border: '1px solid #e6e0d4',
              }}>
                <img
                  src={form.reference_image_url}
                  alt="Foto de referencia"
                  style={{ width: '100%', display: 'block', maxHeight: 220, objectFit: 'cover' }}
                />
                <button
                  type="button"
                  onClick={() => update('reference_image_url', '')}
                  aria-label="Quitar referencia"
                  style={{
                    position: 'absolute', top: 8, right: 8,
                    background: 'rgba(0,0,0,0.6)', color: '#fff',
                    border: 'none', borderRadius: 6,
                    padding: '4px 10px', fontSize: 12,
                    cursor: 'pointer',
                  }}
                >
                  Quitar
                </button>
              </div>
            ) : (
              <div style={{
                border: '1.5px dashed #d4c9b0', borderRadius: 12,
                padding: 16, textAlign: 'center',
                background: 'rgba(45,187,106,0.04)',
              }}>
                <div style={{ fontSize: 12, color: 'var(--ravit-text-muted, #777)', marginBottom: 8 }}>
                  Sube una foto de referencia de la escena
                </div>
                <button
                  type="button"
                  className={shared.btnGhost}
                  style={{ padding: '6px 14px', fontSize: 13 }}
                  onClick={triggerReferencePicker}
                  disabled={uploadingReference}
                >
                  {uploadingReference ? 'Subiendo…' : '↑ Subir'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleReferenceUpload(file);
                    // reset value para permitir re-subir el mismo archivo
                    e.target.value = '';
                  }}
                  style={{ display: 'none' }}
                  aria-label="Seleccionar foto de referencia"
                />
              </div>
            )}

            {/* Filtros de seguridad — UI-INFLU-014.13.fix:
                Antes el checkbox estaba `align-items: center` con un
                <div> de 2 líneas; el check pequeño quedaba flotando
                "muy alto" relativo al texto. Ahora usamos un toggle
                tipo switch a la derecha y el label a la izquierda, que
                replica el diseño Ravit del screenshot original. */}
            <SectionLabel style={{ marginTop: 16 }}>FILTROS DE SEGURIDAD</SectionLabel>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '12px 14px', borderRadius: 10,
              border: '1px solid #e6e0d4', background: '#fff',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>Modo seguro</div>
                <div style={{ fontSize: 12, color: 'var(--ravit-text-muted, #777)', marginTop: 2 }}>
                  Recomendado para producción
                </div>
              </div>
              <ToggleSwitch
                checked={form.safety_mode}
                onChange={(v) => update('safety_mode', v)}
                ariaLabel="Modo seguro"
              />
            </div>
          </div>

          {/* CTA grande Generar */}
          <button
            type="button"
            onClick={handleGenerate}
            disabled={!canGenerate || submitting || overBudget}
            className={shared.btnPrimaryLg}
            style={{ width: '100%', marginTop: 16, justifyContent: 'center' }}
          >
            <span aria-hidden="true">✦</span>
            <span>Generar · {form.count} {form.count === 1 ? 'imagen' : 'imágenes'}</span>
          </button>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            marginTop: 6, fontSize: 12, color: 'var(--ravit-text-muted, #777)',
          }}>
            <span>{costPerAsset} créditos / imagen</span>
            <span><strong>= {totalCost} créditos</strong></span>
          </div>
        </aside>
      </div>
    </div>
  );
}


// ─── Subcomponentes ─────────────────────────────────────────────────────

function PersonaSwitcher({ persona, avatarUrl, variations, category, onEdit, scheduledLabel }) {
  const initials = persona.name?.[0]?.toUpperCase() ?? '?';
  return (
    <div className={shared.card} style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: 12, marginTop: 16,
    }}>
      <div style={{
        width: 56, height: 56, borderRadius: 12,
        overflow: 'hidden', flexShrink: 0,
        background: 'linear-gradient(135deg, #d8c9b0, #b89f7e)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontWeight: 700, fontSize: 24,
      }}>
        {avatarUrl ? (
          <img src={avatarUrl} alt={persona.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : initials}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 10, letterSpacing: '0.08em',
          color: 'var(--ravit-text-muted, #777)', textTransform: 'uppercase',
        }}>
          Generando con
        </div>
        <div style={{ fontWeight: 700, fontSize: 16 }}>
          {persona.name} <span style={{ fontWeight: 400, color: 'var(--ravit-text-muted, #777)' }}>· {category}</span>
        </div>
        {scheduledLabel ? (
          <div style={{ fontSize: 11, color: '#0F7A3F', marginTop: 2 }}>
            {scheduledLabel}
          </div>
        ) : null}
      </div>
      {/* Variation thumbnails */}
      <div style={{ display: 'flex', gap: 4 }}>
        {variations.slice(0, 5).map((v, i) => (
          <div key={v.id || i} style={{
            width: 36, height: 36, borderRadius: 8, overflow: 'hidden',
            background: '#f4ede0', border: '1px solid #e6e0d4',
          }}>
            {v.thumbnail_url || v.url ? (
              <img src={v.thumbnail_url || v.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : null}
          </div>
        ))}
        <button
          type="button"
          onClick={onEdit}
          aria-label="Editar personaje"
          style={{
            width: 36, height: 36, borderRadius: 8,
            border: '1.5px dashed #d4c9b0', background: 'transparent',
            cursor: 'pointer', color: 'var(--ravit-text-muted, #999)',
            fontSize: 18, lineHeight: 1,
          }}
        >+</button>
      </div>
    </div>
  );
}


function FormatCard({ kind, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        position: 'relative', width: '100%', padding: 16,
        borderRadius: 14,
        border: active ? '2px solid #2DBB6A' : '1px solid #e6e0d4',
        background: active ? '#eaf7ef' : '#fff',
        cursor: 'pointer', textAlign: 'left',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}
    >
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: active ? '#2DBB6A' : 'rgba(45,187,106,0.12)',
        color: active ? '#fff' : '#0F7A3F',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 18, marginBottom: 4,
      }}>
        {KIND_ICONS[kind.value] || '◇'}
      </div>
      {kind.badge ? (
        <span style={{
          position: 'absolute', top: 10, right: 10,
          padding: '2px 6px', borderRadius: 6,
          background: '#FFB454', color: '#7a3e00',
          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
        }}>
          {kind.badge}
        </span>
      ) : null}
      <div style={{ fontWeight: 700, fontSize: 15 }}>{kind.label}</div>
      <div style={{ fontSize: 12, color: 'var(--ravit-text-muted, #777)' }}>
        {KIND_SUBLABEL[kind.value] || ''}
      </div>
      <div style={{ fontSize: 12, color: '#0F7A3F', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <span aria-hidden="true">✦</span> {kind.cost} créditos
      </div>
    </button>
  );
}


function ComposerActionButton({ icon, label }) {
  return (
    <button
      type="button"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '6px 12px', borderRadius: 8,
        border: '1px solid #e6e0d4', background: '#fff',
        cursor: 'pointer', fontSize: 13, color: 'var(--ravit-text, #333)',
      }}
    >
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </button>
  );
}


function GenerationThumb({ gen, index, total }) {
  // UI-INFLU-014.13 — preferimos el asset estructurado del backend
  // (`assets[0]` con `{url, mime, duration_s}`). Caemos a `url`/
  // `thumbnail_url` plano por compat con shapes viejos.
  const asset = gen.assets?.[0];
  const url = asset?.url || gen.url || gen.thumbnail_url;
  const isVideo = isVideoAsset(asset, gen.kind);
  const isPending = gen.status === 'queued' || gen.status === 'running';
  const failed = gen.status === 'failed';

  return (
    <div style={{
      position: 'relative', width: '100%', aspectRatio: '3/4',
      borderRadius: 12, overflow: 'hidden',
      background: 'linear-gradient(135deg, #d8c9b0, #b89f7e)',
      border: '1px solid #e6e0d4',
    }}>
      {url && !isPending && !failed ? (
        isVideo ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video
            src={url}
            controls
            preload="metadata"
            style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000' }}
          />
        ) : (
          <img
            src={url}
            alt={`${gen.kind || 'asset'} ${index}`}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        )
      ) : null}
      {isPending ? (
        <div role="status" aria-label="Generación en progreso" style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 12, fontWeight: 600,
          background: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(2px)',
        }}>
          Generando…
        </div>
      ) : null}
      {failed ? (
        <div role="alert" title={gen.error_message || 'Falló la generación'} style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 11, padding: 8, textAlign: 'center',
          background: 'rgba(178,30,30,0.85)',
        }}>
          ✗ Falló
        </div>
      ) : null}
      <div style={{
        position: 'absolute', top: 8, left: 8,
        padding: '2px 8px', borderRadius: 6,
        background: '#2DBB6A', color: '#fff',
        fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
      }}>
        ✦ AI{isVideo ? ' · VIDEO' : ''}
      </div>
      <div style={{
        position: 'absolute', bottom: 8, left: 8,
        padding: '2px 6px', borderRadius: 4,
        background: 'rgba(0,0,0,0.55)', color: '#fff',
        fontSize: 11, fontWeight: 600,
      }}>
        #{index}/{total}
      </div>
      <div style={{
        position: 'absolute', bottom: 8, right: 8,
        display: 'flex', gap: 4,
      }}>
        <button
          type="button"
          aria-label="Like"
          style={{
            width: 28, height: 28, borderRadius: 6,
            background: 'rgba(0,0,0,0.55)', color: '#fff',
            border: 'none', cursor: 'pointer', fontSize: 13,
          }}
        >♡</button>
        <button
          type="button"
          aria-label="Descargar"
          style={{
            width: 28, height: 28, borderRadius: 6,
            background: 'rgba(0,0,0,0.55)', color: '#fff',
            border: 'none', cursor: 'pointer', fontSize: 13,
          }}
        >↓</button>
      </div>
    </div>
  );
}


function SectionLabel({ children, style }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
      color: 'var(--ravit-text-muted, #777)',
      marginTop: 8, marginBottom: 8,
      ...style,
    }}>
      {typeof children === 'string' ? <span>{children}</span> : children}
    </div>
  );
}


/**
 * Toggle switch tipo iOS — reemplaza al <input type="checkbox"> nativo
 * para alinearse con el diseño Ravit y evitar el bug visual donde el
 * checkbox aparecía "muy alto" relativo a un label multi-línea.
 */
function ToggleSwitch({ checked, onChange, ariaLabel }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange?.(!checked)}
      style={{
        position: 'relative',
        width: 42, height: 24, padding: 0,
        borderRadius: 999,
        background: checked ? '#2DBB6A' : '#d4cfc1',
        border: 'none', cursor: 'pointer',
        transition: 'background 120ms ease',
        flexShrink: 0,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute', top: 2,
          left: checked ? 20 : 2,
          width: 20, height: 20, borderRadius: '50%',
          background: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
          transition: 'left 120ms ease',
        }}
      />
    </button>
  );
}


function CompactKpis({ stats }) {
  // KPIs visibles para que el Manager vea performance del personaje sin
  // saltar a otra vista. Compactos abajo del flow de generación.
  const formatReach = (n) => {
    if (!n) return '0';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };
  const formatEng = (r) => `${((Number(r) || 0) * 100).toFixed(1)}%`;
  return (
    <ul aria-label="Métricas del personaje" style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
      gap: 12, marginTop: 32, padding: 0, listStyle: 'none',
    }}>
      <li className={shared.kpiTile}>
        <div className={shared.kpiNumber}>{stats.posts_total ?? 0}</div>
        <div className={shared.kpiLabel}>Posts</div>
      </li>
      <li className={shared.kpiTile}>
        <div className={shared.kpiNumber}>{formatReach(stats.reach_30d)}</div>
        <div className={shared.kpiLabel}>Alcance 30d</div>
      </li>
      <li className={shared.kpiTile}>
        <div className={shared.kpiNumber}>{formatEng(stats.engagement_rate)}</div>
        <div className={shared.kpiLabel}>Engagement</div>
      </li>
    </ul>
  );
}


// Re-export por compatibilidad — el container y los tests viejos pueden
// referenciar `statusLabel` directamente, pero internamente PersonaStudio
// ahora lo consume desde `personaStudioData.js`.
export { statusLabel };
