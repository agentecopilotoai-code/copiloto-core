import { FormField, Modal } from '../../../../components/ui/index.js';
import { MEDIA_ACCEPT, MEDIA_KIND_LABELS, formatBytes } from '../mediaLibraryData.js';
import styles from '../MediaLibraryModule.module.css';

/**
 * Media upload drawer. Reuses the `Modal` primitive; presentational — all state
 * and the upload/file-pick actions come from the `useMediaLibraryData` hook via
 * props. File kind + size are validated in the hook on pick.
 *
 * @param {{
 *   open: boolean,
 *   uploadForm: { kind: string, label: string, description: string, tags: string, file: File|null },
 *   isBusy: boolean,
 *   onChange: (form: object) => void,
 *   onPickFile: (file: File|null) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function MediaUploader({ open, uploadForm, isBusy, onChange, onPickFile, onSubmit, onClose }) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...uploadForm, [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title="Subir medio"
      description="Sube fotos, videos y PDFs del negocio. El bot puede enviarlos durante el agendamiento."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="media-upload-form"
            className={styles.primaryButton}
            disabled={isBusy || !uploadForm.file || !uploadForm.label.trim()}
          >
            {isBusy ? 'Subiendo…' : 'Subir'}
          </button>
        </div>
      }
    >
      <form
        id="media-upload-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField
          label="Archivo"
          required
          hint={
            uploadForm.file
              ? `${MEDIA_KIND_LABELS[uploadForm.kind]} · ${formatBytes(uploadForm.file.size)}`
              : 'Límites: Imagen 5MB · Video 16MB · Audio 16MB · PDF 100MB'
          }
        >
          <input
            type="file"
            required
            accept={MEDIA_ACCEPT}
            onChange={(event) => onPickFile(event.target.files?.[0] || null)}
          />
        </FormField>
        <FormField label="Etiqueta corta" required>
          <input
            type="text"
            required
            maxLength={200}
            value={uploadForm.label}
            onChange={set('label')}
            placeholder="Ej. Lobby principal"
          />
        </FormField>
        <FormField label="Descripción">
          <textarea
            rows={2}
            value={uploadForm.description}
            onChange={set('description')}
            placeholder="Contexto que aparecerá en el panel interno"
          />
        </FormField>
        <FormField label="Tags (separados por coma)">
          <input
            type="text"
            value={uploadForm.tags}
            onChange={set('tags')}
            placeholder="lobby, equipo, procedimiento"
          />
        </FormField>
      </form>
    </Modal>
  );
}
