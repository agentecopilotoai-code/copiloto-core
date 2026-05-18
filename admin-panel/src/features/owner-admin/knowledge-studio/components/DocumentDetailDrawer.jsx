import { FormField, Modal } from '../../../../components/ui/index.js';
import {
  DOCUMENT_TYPE_OPTIONS,
  SOURCE_TYPE_OPTIONS,
  STATUS_OPTIONS,
  VISIBILITY_OPTIONS,
  formatDate,
} from '../knowledgeStudioData.js';
import styles from '../KnowledgeStudio.module.css';

/**
 * Create / edit drawer for a knowledge document. Reuses the `Modal` primitive;
 * presentational — all state and the submit action come from the
 * `useKnowledgeStudioData` hook via props. `active` is intentionally not a
 * selectable status (documents only become active through indexing).
 *
 * @param {{
 *   open: boolean,
 *   form: object,
 *   editingId: string | null,
 *   editingDocument: object | null,
 *   isSaving: boolean,
 *   onFieldChange: (field: string, value: string) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function DocumentDetailDrawer({
  open,
  form,
  editingId,
  editingDocument,
  isSaving,
  onFieldChange,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  const set = (field) => (event) => onFieldChange(field, event.target.value);

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={editingId ? 'Editar documento' : 'Nuevo documento'}
      description="Cargá preguntas frecuentes, políticas y otros documentos de referencia para que el bot pueda consultarlos. Después de subir, usá «Indexar» para que el bot empiece a usar el contenido."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="knowledge-doc-form"
            className={styles.primaryButton}
            disabled={isSaving || !form.title.trim()}
          >
            {isSaving ? 'Guardando…' : editingId ? 'Actualizar' : 'Crear documento'}
          </button>
        </div>
      }
    >
      <form
        id="knowledge-doc-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Título" required>
          <input type="text" required value={form.title} onChange={set('title')} />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Tipo">
            <select value={form.document_type} onChange={set('document_type')}>
              {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Fuente">
            <select value={form.source_type} onChange={set('source_type')}>
              {SOURCE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Visibilidad">
            <select value={form.visibility} onChange={set('visibility')}>
              {VISIBILITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Estado">
            <select value={form.status} onChange={set('status')}>
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
              <option value="active" disabled>
                Active (solo por indexado)
              </option>
            </select>
          </FormField>
        </div>
        <FormField label="FAQ / política manual">
          <textarea
            rows={4}
            value={form.content}
            onChange={set('content')}
            placeholder="Pregunta/respuesta, política operativa o contenido de referencia."
          />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="URI de fuente u object key">
            <input
              type="text"
              value={form.source_uri}
              onChange={set('source_uri')}
              placeholder="s3://bucket/key.pdf o https://…"
            />
          </FormField>
          <FormField label="MIME type">
            <input
              type="text"
              value={form.mime_type}
              onChange={set('mime_type')}
              placeholder="application/pdf"
            />
          </FormField>
          <FormField label="Checksum">
            <input
              type="text"
              value={form.checksum}
              onChange={set('checksum')}
              placeholder="sha256 opcional"
            />
          </FormField>
        </div>
        {editingId && editingDocument ? (
          <p className={styles.hint}>
            Editando {editingId} · actualizado {formatDate(editingDocument.updated_at)}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
