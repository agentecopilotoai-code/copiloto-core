import { useRef, useState } from 'react';

import { Button, Card, FormField } from '../../../../components/ui/index.js';
import {
  BOT_EMOJI_OPTIONS,
  BOT_FORMALITY_OPTIONS,
  BOT_TONE_OPTIONS,
  DEFAULT_BOT_PERSONALITY,
  PERSONALITY_PREVIEW_SAMPLES,
} from '../tenantSetupData.js';
import { renderPersonalityPreview } from '../tenantSetupTransforms.js';
import styles from '../TenantSetupWizard.module.css';

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
    <>
      <Card padding="md">
        <h3 className={styles.sectionTitle}>Voz del bot</h3>
        <p className={styles.hint}>
          Configura cómo suena tu bot: tono, trato y nivel de emojis. Esto se inyecta
          como bloque dedicado antes del template RAG; las respuestas cambian sin tocar
          el contenido del catálogo. Los cambios aplican al guardar Settings.
        </p>

        <form
          className={styles.formGrid}
          onSubmit={(event) => { event.preventDefault(); handleSaveSettings(event); }}
        >
          <fieldset className={`${styles.fieldset} ${styles.wide}`}>
            <legend>Tono</legend>
            <div className={styles.optionGrid}>
              {BOT_TONE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`${styles.providerCard} ${botPersonality.tone === opt.value ? styles.selected : ''}`}
                >
                  <input
                    type="radio"
                    name="bot-tone"
                    value={opt.value}
                    checked={botPersonality.tone === opt.value}
                    onChange={() => setBotPersonality((prev) => ({ ...prev, tone: opt.value }))}
                  />
                  <strong>{opt.label}</strong>
                  <small className={styles.hint}>{opt.hint}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className={`${styles.fieldset} ${styles.wide}`}>
            <legend>Trato</legend>
            <div className={styles.optionGrid}>
              {BOT_FORMALITY_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`${styles.providerCard} ${botPersonality.formality === opt.value ? styles.selected : ''}`}
                >
                  <input
                    type="radio"
                    name="bot-formality"
                    value={opt.value}
                    checked={botPersonality.formality === opt.value}
                    onChange={() => setBotPersonality((prev) => ({ ...prev, formality: opt.value }))}
                  />
                  <strong>{opt.label}</strong>
                  <small className={styles.hint}>{opt.hint}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className={`${styles.fieldset} ${styles.wide}`}>
            <legend>Emojis</legend>
            <div className={styles.optionGrid}>
              {BOT_EMOJI_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`${styles.providerCard} ${botPersonality.emoji_level === opt.value ? styles.selected : ''}`}
                >
                  <input
                    type="radio"
                    name="bot-emoji"
                    value={opt.value}
                    checked={botPersonality.emoji_level === opt.value}
                    onChange={() => setBotPersonality((prev) => ({ ...prev, emoji_level: opt.value }))}
                  />
                  <strong>{opt.label}</strong>
                  <small className={styles.hint}>{opt.hint}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <FormField
            label="Persona personalizada (opcional, máx 600 caracteres)"
            hint={`${botPersonality.custom_persona.length}/600`}
            className={styles.wide}
          >
            <textarea
              rows={3}
              maxLength={600}
              placeholder="Ej: Eres una recepcionista experta en spa de lujo; cuidas cada detalle y das opciones premium primero."
              value={botPersonality.custom_persona}
              onChange={(e) => setBotPersonality((prev) => ({ ...prev, custom_persona: e.target.value }))}
            />
          </FormField>

          <div className={`${styles.builderPreview} ${styles.wide}`}>
            <strong>Vista previa</strong>
            <p className={styles.hint}>
              Estos ejemplos se renderizan con tu configuración actual. Son aproximaciones del
              cliente — el modelo final puede variar pero respeta el bloque de voz inyectado.
            </p>
            <ul className={styles.previewList}>
              {PERSONALITY_PREVIEW_SAMPLES.map((sample) => (
                <li key={sample.id} className={styles.previewItem}>
                  <strong>{sample.title}</strong>
                  <div className={styles.previewBubble}>
                    {renderPersonalityPreview(sample, botPersonality, tenantForm.display_name)}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className={`${styles.actions} ${styles.wide}`}>
            <Button
              variant="secondary"
              type="button"
              onClick={() => setBotPersonality({ ...DEFAULT_BOT_PERSONALITY })}
              disabled={isBusy}
            >
              Restablecer
            </Button>
            <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
              {isBusy ? 'Guardando…' : 'Guardar voz del bot'}
            </Button>
          </div>
        </form>
      </Card>

      {/* UI-012-FU: branding logo uploader. Lives next to the bot voice
          because both shape how the tenant presents itself in the admin
          shell. Behind the same tenant_setup.write boundary as the rest
          of the wizard via the wrapper in TenantSetupWizard.jsx. */}
      <Card padding="md" aria-labelledby="brand-logo-heading">
        <h3 id="brand-logo-heading" className={styles.sectionTitle}>Logo de marca</h3>
        <p className={styles.hint}>
          Sube el logo del tenant (PNG, JPEG o WEBP, máx. 5 MB). Aparecerá en el
          topbar del panel admin y en cualquier vista que ya use el slot de
          branding. SVG no se acepta por seguridad — usa PNG con fondo
          transparente para el mismo efecto visual.
        </p>

        <div className={styles.brandLogoPreview} aria-live="polite">
          {brandLogoUrl ? (
            <img
              src={brandLogoUrl}
              alt={`Logo actual de ${tenantForm.display_name || 'el tenant'}`}
              className={styles.brandLogoImg}
            />
          ) : (
            <p className={styles.hint} data-testid="brand-logo-empty">
              No hay logo cargado todavía. Se mostrarán las iniciales del tenant.
            </p>
          )}
        </div>

        <form
          className={styles.formGrid}
          onSubmit={onUploadLogo}
          aria-label="Subir logo de marca del tenant"
        >
          <FormField label="Archivo de imagen" hint="PNG, JPEG o WEBP. Máx 5 MB." className={styles.wide}>
            <input
              ref={fileInputRef}
              type="file"
              accept={LOGO_ACCEPT_MIME}
              onChange={(e) => setPendingLogoFile(e.target.files?.[0] || null)}
              data-testid="brand-logo-file-input"
            />
          </FormField>

          <div className={`${styles.actions} ${styles.wide}`}>
            <Button
              variant="primary"
              type="submit"
              disabled={isBusy || !currentTenantId || !pendingLogoFile}
            >
              {isBusy ? 'Subiendo…' : 'Subir logo'}
            </Button>
            {brandLogoUrl ? (
              <Button
                variant="secondary"
                type="button"
                onClick={() => handleClearBrandLogo?.()}
                disabled={isBusy || !currentTenantId}
              >
                Quitar logo
              </Button>
            ) : null}
          </div>
        </form>
      </Card>
    </>
  );
}
