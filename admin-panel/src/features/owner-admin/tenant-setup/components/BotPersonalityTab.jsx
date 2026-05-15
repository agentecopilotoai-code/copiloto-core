import { useRef, useState } from 'react';

import {
  BOT_EMOJI_OPTIONS,
  BOT_FORMALITY_OPTIONS,
  BOT_TONE_OPTIONS,
  DEFAULT_BOT_PERSONALITY,
  PERSONALITY_PREVIEW_SAMPLES,
} from '../tenantSetupData.js';
import { renderPersonalityPreview } from '../tenantSetupTransforms.js';

const LOGO_ACCEPT_MIME = 'image/png,image/jpeg,image/webp';

export function BotPersonalityTab({ state, actions }) {
  const { botPersonality, tenantForm, isBusy, currentTenantId, brandLogoUrl } = state;
  const {
    handleSaveSettings,
    setBotPersonality,
    handleUploadBrandLogo,
    handleClearBrandLogo,
  } = actions;
  const fileInputRef = useRef(null);
  const [pendingLogoFile, setPendingLogoFile] = useState(null);

  async function onUploadLogo(event) {
    event.preventDefault();
    if (!pendingLogoFile) return;
    const result = await handleUploadBrandLogo?.(pendingLogoFile);
    if (result) {
      setPendingLogoFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  return (
    <div className="wizard-panel voz-bot-panel">
      <div className="voz-bot-header">
        <h3>Voz del bot</h3>
        <p className="hint">
          Configura cómo suena tu bot: tono, trato y nivel de emojis. Esto se inyecta
          como bloque dedicado antes del template RAG; las respuestas cambian sin tocar
          el contenido del catálogo. Los cambios aplican al guardar Settings.
        </p>
      </div>

      <form
        className="voz-bot-form form-grid"
        onSubmit={(event) => { event.preventDefault(); handleSaveSettings(event); }}
      >
        <fieldset className="wide">
          <legend>Tono</legend>
          <div className="option-grid">
            {BOT_TONE_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`option-card ${botPersonality.tone === opt.value ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="bot-tone"
                  value={opt.value}
                  checked={botPersonality.tone === opt.value}
                  onChange={() => setBotPersonality((prev) => ({ ...prev, tone: opt.value }))}
                />
                <strong>{opt.label}</strong>
                <small>{opt.hint}</small>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="wide">
          <legend>Trato</legend>
          <div className="option-grid">
            {BOT_FORMALITY_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`option-card ${botPersonality.formality === opt.value ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="bot-formality"
                  value={opt.value}
                  checked={botPersonality.formality === opt.value}
                  onChange={() => setBotPersonality((prev) => ({ ...prev, formality: opt.value }))}
                />
                <strong>{opt.label}</strong>
                <small>{opt.hint}</small>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="wide">
          <legend>Emojis</legend>
          <div className="option-grid">
            {BOT_EMOJI_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`option-card ${botPersonality.emoji_level === opt.value ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="bot-emoji"
                  value={opt.value}
                  checked={botPersonality.emoji_level === opt.value}
                  onChange={() => setBotPersonality((prev) => ({ ...prev, emoji_level: opt.value }))}
                />
                <strong>{opt.label}</strong>
                <small>{opt.hint}</small>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="wide">
          <span>Persona personalizada (opcional, máx 600 caracteres)</span>
          <textarea
            rows={3}
            maxLength={600}
            placeholder="Ej: Eres una recepcionista experta en spa de lujo; cuidas cada detalle y das opciones premium primero."
            value={botPersonality.custom_persona}
            onChange={(e) => setBotPersonality((prev) => ({ ...prev, custom_persona: e.target.value }))}
          />
          <small className="hint">
            {botPersonality.custom_persona.length}/600
          </small>
        </label>

        <div className="voz-bot-preview wide">
          <h4>Vista previa</h4>
          <p className="hint">
            Estos ejemplos se renderizan con tu configuración actual. Son aproximaciones del
            cliente — el modelo final puede variar pero respeta el bloque de voz inyectado.
          </p>
          <ul className="preview-list">
            {PERSONALITY_PREVIEW_SAMPLES.map((sample) => (
              <li key={sample.id} className="preview-item">
                <strong>{sample.title}</strong>
                <div className="preview-bubble">
                  {renderPersonalityPreview(sample, botPersonality, tenantForm.display_name)}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="form-actions wide">
          <button
            className="secondary-action"
            type="button"
            onClick={() => setBotPersonality({ ...DEFAULT_BOT_PERSONALITY })}
            disabled={isBusy}
          >
            Restablecer
          </button>
          <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
            {isBusy ? 'Guardando…' : 'Guardar voz del bot'}
          </button>
        </div>
      </form>

      {/* UI-012-FU: branding logo uploader. Lives next to the bot voice
          because both shape how the tenant presents itself in the admin
          shell. Behind the same tenant_setup.write boundary as the rest
          of the wizard via moduleRegistry. */}
      <section className="wizard-panel brand-logo-panel" aria-labelledby="brand-logo-heading">
        <header className="voz-bot-header">
          <h3 id="brand-logo-heading">Logo de marca</h3>
          <p className="hint">
            Sube el logo del tenant (PNG, JPEG o WEBP, máx. 5 MB). Aparecerá en el
            topbar del panel admin y en cualquier vista que ya use el slot de
            branding. SVG no se acepta por seguridad — usa PNG con fondo
            transparente para el mismo efecto visual.
          </p>
        </header>

        <div className="brand-logo-preview" aria-live="polite">
          {brandLogoUrl ? (
            <img
              src={brandLogoUrl}
              alt={`Logo actual de ${tenantForm.display_name || 'el tenant'}`}
              style={{ maxWidth: 120, maxHeight: 120, borderRadius: 8 }}
            />
          ) : (
            <p className="hint" data-testid="brand-logo-empty">
              No hay logo cargado todavía. Se mostrarán las iniciales del tenant.
            </p>
          )}
        </div>

        <form
          className="form-grid"
          onSubmit={onUploadLogo}
          aria-label="Subir logo de marca del tenant"
        >
          <label className="wide">
            <span>Archivo de imagen</span>
            <input
              ref={fileInputRef}
              type="file"
              accept={LOGO_ACCEPT_MIME}
              onChange={(e) => setPendingLogoFile(e.target.files?.[0] || null)}
              data-testid="brand-logo-file-input"
            />
            <small className="hint">PNG, JPEG o WEBP. Máx 5 MB.</small>
          </label>

          <div className="form-actions wide">
            <button
              className="primary-action"
              type="submit"
              disabled={isBusy || !currentTenantId || !pendingLogoFile}
            >
              {isBusy ? 'Subiendo…' : 'Subir logo'}
            </button>
            {brandLogoUrl ? (
              <button
                className="secondary-action"
                type="button"
                onClick={() => handleClearBrandLogo?.()}
                disabled={isBusy || !currentTenantId}
              >
                Quitar logo
              </button>
            ) : null}
          </div>
        </form>
      </section>
    </div>
  );
}
