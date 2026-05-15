import { StatusBadge } from '../../../../components/ui/index.js';
import { ConversationListItem } from '../../../../components/domain/index.js';
import { sortConversations } from '../../inbox/inboxData.js';
import { HANDOFF_FILTERS, toHandoffRow } from '../myHandoffsData.js';
import styles from '../MyHandoffs.module.css';

/**
 * MyHandoffsList — la cola de handoffs del agente.
 *
 * Reutiliza el componente de dominio `ConversationListItem` (el mismo que usa
 * `InboxList` del Inbox) para pintar cada conversación escalada, y le añade
 * encima sólo las tabs específicas de handoff (`Todos` / `Sin asignar` /
 * `Mías`) que el Inbox no tiene. `InboxList` no se reusa tal cual porque su API
 * está acoplada al form «iniciar conversación» y a las tabs `Todas` / `Quejas`;
 * el backlog admite explícitamente caer a `ConversationListItem` cuando
 * `InboxList` no acepta limpiamente una lista pre-filtrada + tabs custom.
 *
 * Presentacional: recibe la lista ya filtrada por `useMyHandoffsData`. La
 * acción «Tomar» selecciona la conversación y dispara `acceptHandoff` (la
 * acción de handoff del Inbox, reusada verbatim) — no inventa endpoints.
 *
 * @param {object} props
 * @param {Array<object>} props.handoffs — conversaciones escaladas ya filtradas
 * @param {{ all: number, unassigned: number, mine: number }} props.counts
 * @param {'all'|'unassigned'|'mine'} props.handoffFilter
 * @param {string|null} props.currentUserId
 * @param {string|null} props.selectedConversationId
 * @param {boolean} props.isBusy
 * @param {(filterId: string) => void} props.onFilterChange
 * @param {(id: string) => void} props.onSelectConversation
 * @param {(id: string) => void} props.onTakeHandoff
 */
export function MyHandoffsList({
  handoffs,
  counts,
  handoffFilter,
  currentUserId,
  selectedConversationId,
  isBusy,
  onFilterChange,
  onSelectConversation,
  onTakeHandoff,
}) {
  return (
    <section className={styles.queue} aria-label="Cola de handoffs">
      <div role="tablist" aria-label="Filtro de handoffs" className={styles.tabs}>
        {HANDOFF_FILTERS.map((filter) => (
          <button
            key={filter.id}
            type="button"
            role="tab"
            aria-selected={handoffFilter === filter.id}
            className={[styles.tab, handoffFilter === filter.id ? styles.tabActive : '']
              .filter(Boolean)
              .join(' ')}
            onClick={() => onFilterChange(filter.id)}
          >
            {filter.label} ({counts[filter.id] ?? 0})
          </button>
        ))}
      </div>

      {handoffs.length === 0 ? (
        <p className={styles.empty}>
          {handoffFilter === 'mine'
            ? 'No tienes handoffs asignados ahora mismo.'
            : handoffFilter === 'unassigned'
              ? 'No hay handoffs sin asignar en este tenant.'
              : 'No hay conversaciones escaladas a humano en este tenant.'}
        </p>
      ) : (
        <ul className={styles.list}>
          {sortConversations(handoffs).map((conversation) => {
            const row = toHandoffRow(conversation, currentUserId);
            return (
              <li key={row.id} className={styles.row}>
                <ConversationListItem
                  data-handoff-ownership={row.isMine ? 'mine' : row.isUnassigned ? 'unassigned' : 'colleague'}
                  selected={row.id === selectedConversationId}
                  onSelect={() => onSelectConversation(row.id)}
                  title={row.contactLabel}
                  statusText={row.statusText}
                  preview={row.intent ? `Intención: ${row.intent}` : 'Escalada a humano'}
                  timestamp={`Esperando desde ${row.waitingSince}`}
                  badges={(
                    <StatusBadge tone={row.isUnassigned ? 'danger' : row.isMine ? 'accent' : 'neutral'}>
                      {row.ownership}
                    </StatusBadge>
                  )}
                />
                <div className={styles.rowActions}>
                  {row.isUnassigned ? (
                    <button
                      type="button"
                      className={styles.takeButton}
                      disabled={isBusy}
                      onClick={() => onTakeHandoff(row.id)}
                    >
                      Tomar
                    </button>
                  ) : (
                    <span className={styles.rowMeta}>
                      {row.isMine ? 'Asignada a ti' : 'Asignada a otro agente'}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
