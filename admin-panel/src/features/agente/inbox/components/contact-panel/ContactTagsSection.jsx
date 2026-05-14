import { TagPill } from '../../../../../components/domain/index.js';
import styles from '../../OperationsDesk.module.css';

/**
 * ContactTagsSection — the contact's tags + internal-note affordances inside
 * the side panel. Presentational; the assign / remove / note handlers live in
 * `useContactPanelData`. Ported verbatim from the legacy `OperationsDesk`.
 *
 * @param {object} props
 * @param {Array<object>} props.tags — the contact's current tags
 * @param {Array<object>} props.contactTags — the tenant's tag catalogue
 * @param {string} props.pendingTagAssign
 * @param {string} props.quickNote
 * @param {boolean} props.isBusy
 * @param {(tagId: string) => void} props.onPendingTagChange
 * @param {(note: string) => void} props.onQuickNoteChange
 * @param {(event: Event) => void} props.onAssignTag
 * @param {(tagId: string) => void} props.onRemoveTag
 * @param {(event: Event) => void} props.onQuickNote
 */
export function ContactTagsSection({
  tags,
  contactTags,
  pendingTagAssign,
  quickNote,
  isBusy,
  onPendingTagChange,
  onQuickNoteChange,
  onAssignTag,
  onRemoveTag,
  onQuickNote,
}) {
  return (
    <div className="handoff-panel" aria-label="Etiquetas y notas del contacto">
      <div>
        <strong>Etiquetas y notas</strong>
        <p className="hint">
          Clasifica al contacto y deja una nota interna visible solo para el equipo.
        </p>
      </div>
      <div className={styles.tagRow}>
        {tags.map((tag) => (
          <TagPill
            key={tag.id}
            tag={tag}
            onRemove={() => onRemoveTag(tag.id)}
            disabled={isBusy}
          />
        ))}
      </div>
      <form className="action-row" onSubmit={onAssignTag}>
        <select
          value={pendingTagAssign}
          onChange={(event) => onPendingTagChange(event.target.value)}
        >
          <option value="">— Asignar etiqueta —</option>
          {contactTags.map((tag) => (
            <option key={tag.id} value={tag.id}>{tag.name}</option>
          ))}
        </select>
        <button className="secondary-action" type="submit" disabled={!pendingTagAssign || isBusy}>
          Asignar
        </button>
      </form>
      <form className={`action-row ${styles.quickNoteRow}`} onSubmit={onQuickNote}>
        <input
          aria-label="Nota interna rápida"
          placeholder="Nota interna rápida"
          value={quickNote}
          onChange={(event) => onQuickNoteChange(event.target.value)}
        />
        <button className="secondary-action" type="submit" disabled={!quickNote.trim() || isBusy}>
          Guardar nota
        </button>
      </form>
    </div>
  );
}
