import { useState } from 'react';

import { Card, CardHeader } from '../../../../components/ui/index.js';
import { TagPill } from '../../../../components/domain/index.js';
import styles from '../ConversationsContacts.module.css';

/**
 * Tags panel of the contact drawer: the contact's assigned tags (removable)
 * plus the "assign tag" select. Presentational — `onAssign`/`onRemove` come
 * from the data hook.
 *
 * @param {{
 *   tags: Array<object>,
 *   unassignedTags: Array<object>,
 *   isBusy: boolean,
 *   onAssign: (tagId: string) => void,
 *   onRemove: (tagId: string) => void,
 * }} props
 */
export function ContactTagsPanel({ tags, unassignedTags, isBusy, onAssign, onRemove }) {
  const [pendingTagId, setPendingTagId] = useState('');

  function handleAssign(event) {
    event.preventDefault();
    if (!pendingTagId) return;
    onAssign(pendingTagId);
    setPendingTagId('');
  }

  return (
    <Card padding="md">
      <CardHeader title="Etiquetas" subtitle="Segmentación manual del contacto" />
      <div className={styles.tagRow}>
        {tags.length > 0 ? (
          tags.map((tag) => (
            <TagPill key={tag.id} tag={tag} onRemove={() => onRemove(tag.id)} disabled={isBusy} />
          ))
        ) : (
          <span className={styles.muted}>Sin etiquetas asignadas.</span>
        )}
      </div>
      <form className={styles.inlineForm} onSubmit={handleAssign}>
        <select
          value={pendingTagId}
          onChange={(event) => setPendingTagId(event.target.value)}
          disabled={isBusy || unassignedTags.length === 0}
        >
          <option value="">— Asignar etiqueta —</option>
          {unassignedTags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
        <button type="submit" className={styles.secondaryButton} disabled={!pendingTagId || isBusy}>
          Asignar
        </button>
      </form>
    </Card>
  );
}
