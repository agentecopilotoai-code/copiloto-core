import { FormField, Modal } from '../../../../components/ui/index.js';
import { DOCUMENT_TYPE_OPTIONS, VISIBILITY_OPTIONS } from '../knowledgeStudioData.js';
import styles from '../KnowledgeStudio.module.css';

const ACCEPTED_FILES =
  '.txt,.md,.markdown,.csv,.json,.pdf,.docx,text/plain,text/markdown,text/csv,application/json,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/**
 * File-upload drawer. Reuses the `Modal` primitive; presentational — all state
 * and the upload action come from the `useKnowledgeStudioData` hook via props.
 * TXT/MD/CSV/JSON extract instantly; PDF/DOCX extract in the background.
 *
 * @param {{
 *   open: boolean,
 *   uploadForm: { title: string, document_type: string, visibility: string, file: File|null },
 *   isUploading: boolean,
 *   onChange: (form: object) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function DocumentUploader({ open, uploadForm, isUploading, onChange, onSubmit, onClose }) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...uploadForm, [key]: event.target.value });
  const canSubmit = Boolean(uploadForm.file) && uploadForm.title.trim() && !isUploading;

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title="Subir documento"
      description="Guarda archivos en el backend de conocimiento. TXT, Markdown, CSV y JSON se extraen al instante; PDF y DOCX se extraen en segundo plano."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="knowledge-upload-form"
            className={styles.primaryButton}
            disabled={!canSubmit}
          >
            {isUploading ? 'Subiendo…' : 'Guardar archivo'}
          </button>
        </div>
      }
    >
      <form
        id="knowledge-upload-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Título del archivo" required>
          <input type="text" required value={uploadForm.title} onChange={set('title')} />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Tipo">
            <select value={uploadForm.document_type} onChange={set('document_type')}>
              {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Visibilidad">
            <select value={uploadForm.visibility} onChange={set('visibility')}>
              {VISIBILITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FormField>
        </div>
        <FormField label="Archivo">
          <input
            type="file"
            required
            accept={ACCEPTED_FILES}
            onChange={(event) =>
              onChange({ ...uploadForm, file: event.target.files?.[0] || null })
            }
          />
        </FormField>
      </form>
    </Modal>
  );
}
