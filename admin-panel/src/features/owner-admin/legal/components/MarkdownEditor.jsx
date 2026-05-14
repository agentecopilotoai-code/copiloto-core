import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { KIND_LABELS, KIND_ORDER, renderPreview } from '../legalData.js';
import styles from '../LegalModule.module.css';

/**
 * Side-by-side Markdown editor for a new legal-document draft: kind/language/
 * title fields + a textarea and a live sanitised preview. Presentational — all
 * state and the save action come from the `useLegalData` hook via props. The
 * preview uses the safe Markdown-subset renderer (`renderPreview`) — no raw
 * HTML reaches `dangerouslySetInnerHTML`.
 *
 * @param {{
 *   form: { kind: string, language: string, title: string, content_md: string },
 *   saving: boolean,
 *   tenantId: string | undefined,
 *   onFieldChange: (patch: object) => void,
 *   onSubmit: () => void,
 * }} props
 */
export function MarkdownEditor({ form, saving, tenantId, onFieldChange, onSubmit }) {
  const previewHtml = renderPreview(form.content_md);

  return (
    <Card padding="md">
      <CardHeader
        title="Editor · Markdown"
        subtitle="Vista previa con la misma sanitización que la URL pública (subset Markdown, sin HTML embebido)."
      />
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
        aria-label="Nuevo borrador legal"
      >
        <div className={styles.formRow}>
          <FormField label="Tipo">
            <select
              value={form.kind}
              onChange={(event) => onFieldChange({ kind: event.target.value })}
            >
              {KIND_ORDER.map((kind) => (
                <option key={kind} value={kind}>
                  {KIND_LABELS[kind]}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Idioma">
            <input
              type="text"
              maxLength={8}
              value={form.language}
              onChange={(event) => onFieldChange({ language: event.target.value })}
              placeholder="es"
            />
          </FormField>
          <FormField label="Título" required>
            <input
              type="text"
              required
              maxLength={200}
              value={form.title}
              onChange={(event) => onFieldChange({ title: event.target.value })}
              placeholder="Política de Privacidad — Spa La Florida"
            />
          </FormField>
        </div>
        <div className={styles.editorGrid}>
          <FormField label="Contenido (Markdown)">
            <textarea
              required
              rows={18}
              value={form.content_md}
              onChange={(event) => onFieldChange({ content_md: event.target.value })}
              placeholder={'# Aviso de Privacidad\n\nResponsable del tratamiento: ...'}
            />
          </FormField>
          <div className={styles.previewPane}>
            <span className={styles.previewLabel}>Vista previa renderizada</span>
            <div
              className={styles.preview}
              // Sanitised by renderPreview (HTML-escaped, Markdown subset only).
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
        <div className={styles.formActions}>
          <button
            type="submit"
            className={styles.primaryButton}
            disabled={saving || !tenantId}
          >
            {saving ? 'Guardando…' : 'Crear borrador'}
          </button>
        </div>
      </form>
    </Card>
  );
}
