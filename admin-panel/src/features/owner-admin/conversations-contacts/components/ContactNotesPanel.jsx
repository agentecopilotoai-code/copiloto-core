import { useState } from 'react';

import { Card, CardHeader } from '../../../../components/ui/index.js';
import { TimelineEntry } from '../../../../components/domain/index.js';
import { formatDate } from '../contactsFormat.js';
import styles from '../ConversationsContacts.module.css';

/**
 * Internal notes panel of the contact drawer: the "add note" form and the list
 * of team-only notes. Presentational — `onCreate` comes from the data hook.
 *
 * @param {{
 *   notes: Array<object>,
 *   isBusy: boolean,
 *   onCreate: (body: string) => void,
 * }} props
 */
export function ContactNotesPanel({ notes, isBusy, onCreate }) {
  const [draft, setDraft] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    const body = draft.trim();
    if (!body) return;
    onCreate(body);
    setDraft('');
  }

  return (
    <Card padding="md">
      <CardHeader title="Notas internas" subtitle="Visibles solo para el equipo" />
      <form className={styles.noteForm} onSubmit={handleSubmit}>
        <textarea
          className={styles.noteTextarea}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={2}
          placeholder="Agrega una nota visible solo para el equipo"
        />
        <button
          type="submit"
          className={styles.primaryButton}
          disabled={!draft.trim() || isBusy}
        >
          Guardar nota
        </button>
      </form>
      {notes && notes.length > 0 ? (
        <ul className={styles.timelineList}>
          {notes.map((note) => (
            <TimelineEntry
              key={note.id}
              meta={`${note.created_by_name || 'Equipo'} · ${formatDate(note.created_at)}`}
            >
              {note.body}
            </TimelineEntry>
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>Sin notas todavía.</p>
      )}
    </Card>
  );
}
