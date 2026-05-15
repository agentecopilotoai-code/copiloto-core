import { ConversationListItem } from '../../../../components/domain/index.js';
import { StatusBadge } from '../../../../components/ui/index.js';
import { formatDate, parseMeta, sortConversations, statusLabel } from '../inboxData.js';
import styles from '../OperationsDesk.module.css';

/**
 * InboxList — the conversation list with the `Todas` / `Quejas` filter tabs and
 * (optionally) the "iniciar conversación" form. Reuses the shared
 * `ConversationListItem` domain component. Presentational: every list item,
 * badge, the urgency-first sort and the `data-urgent` / `data-complaint`
 * attributes are ported verbatim from the legacy `OperationsDesk`.
 *
 * @param {object} props
 * @param {Array<object>} props.conversations
 * @param {Array<object>} props.complaints
 * @param {'all'|'complaints'} props.inboxFilter
 * @param {string|null} props.selectedConversationId
 * @param {object} [props.startForm] — required when `showStartForm` is true.
 * @param {boolean} [props.isBusy]
 * @param {boolean} [props.showStartForm=true] — render the "Iniciar conversación"
 *   form at the top of the list. Default `true` preserves the legacy behavior
 *   used by `OperationsDesk`. The Viewer read-only conversations view
 *   (UI-010.4) passes `false` so the start-form (a write action) is omitted,
 *   per the UI-010 criterio global («100% de las acciones write deben estar
 *   ocultas»).
 * @param {(filter: string) => void} props.onFilterChange
 * @param {(id: string) => void} props.onSelectConversation
 * @param {(form: object) => void} [props.onStartFormChange] — required when
 *   `showStartForm` is true.
 * @param {(event: Event) => void} [props.onStartConversation] — required when
 *   `showStartForm` is true.
 */
export function InboxList({
  conversations,
  complaints,
  inboxFilter,
  selectedConversationId,
  startForm,
  isBusy,
  showStartForm = true,
  onFilterChange,
  onSelectConversation,
  onStartFormChange,
  onStartConversation,
}) {
  return (
    <aside className={`conversation-list ${styles.inboxList}`} aria-label="Conversaciones">
      {showStartForm ? (
      <form className={`start-conversation-panel ${styles.startForm}`} onSubmit={onStartConversation}>
        <div>
          <strong>Iniciar conversación</strong>
          <p className="hint">
            Crea o reutiliza una conversación abierta y encola el primer mensaje outbound. El
            worker cambiará el estado queued/sent/failed según la respuesta de WhatsApp.
          </p>
        </div>
        <label>
          Teléfono WhatsApp E.164
          <input
            onChange={(event) => onStartFormChange({ ...startForm, phone: event.target.value })}
            placeholder="+573001112233"
            value={startForm.phone}
          />
        </label>
        <label>
          Nombre del contacto
          <input
            onChange={(event) => onStartFormChange({ ...startForm, displayName: event.target.value })}
            placeholder="Nombre visible (opcional)"
            value={startForm.displayName}
          />
        </label>
        <label>
          Tipo de mensaje
          <select
            onChange={(event) => onStartFormChange({ ...startForm, type: event.target.value })}
            value={startForm.type}
          >
            <option value="text">Texto</option>
            <option value="image">Imagen</option>
            <option value="video">Video</option>
            <option value="audio">Audio</option>
          </select>
        </label>
        <label>
          MIME type
          <input
            onChange={(event) => onStartFormChange({ ...startForm, mimeType: event.target.value })}
            placeholder="image/jpeg, video/mp4, audio/ogg"
            value={startForm.mimeType}
          />
        </label>
        <label>
          Media ID Meta
          <input
            onChange={(event) => onStartFormChange({ ...startForm, mediaId: event.target.value })}
            placeholder="ID del media subido a WhatsApp"
            value={startForm.mediaId}
          />
        </label>
        <label>
          URL pública media
          <input
            onChange={(event) => onStartFormChange({ ...startForm, mediaUrl: event.target.value })}
            placeholder="https://..."
            value={startForm.mediaUrl}
          />
        </label>
        <label className="wide">
          Mensaje inicial / caption
          <textarea
            onChange={(event) =>
              onStartFormChange({ ...startForm, initialMessage: event.target.value })}
            placeholder="Texto para mensajes de texto o caption para imagen/video..."
            value={startForm.initialMessage}
          />
        </label>
        <button
          className="primary-action"
          disabled={
            isBusy
            || !startForm.phone.trim()
            || (startForm.type === 'text' && !startForm.initialMessage.trim())
          }
          type="submit"
        >
          Iniciar conversación
        </button>
      </form>
      ) : null}

      <div
        role="tablist"
        aria-label="Filtro de inbox"
        className={styles.inboxTabs}
      >
        <button
          type="button"
          role="tab"
          aria-selected={inboxFilter === 'all'}
          className={`tab ${inboxFilter === 'all' ? 'active' : ''}`}
          onClick={() => onFilterChange('all')}
        >
          Todas ({conversations.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={inboxFilter === 'complaints'}
          className={`tab ${inboxFilter === 'complaints' ? 'active' : ''}`}
          onClick={() => onFilterChange('complaints')}
          title="Conversaciones escaladas por feedback negativo"
        >
          Quejas ({complaints.length})
        </button>
      </div>

      {inboxFilter === 'complaints' ? (
        <>
          {complaints.length === 0 ? (
            <p className="hint">No hay quejas activas en este tenant.</p>
          ) : null}
          {complaints.map((complaint) => (
            <ConversationListItem
              key={complaint.id}
              data-complaint="negative_feedback"
              selected={complaint.id === selectedConversationId}
              onSelect={() => onSelectConversation(complaint.id)}
              title={complaint.contact_label || complaint.contact_id}
              statusText={complaint.feedback_rating != null ? `${complaint.feedback_rating} ★` : 'Queja'}
              badges={<StatusBadge tone="danger">Atención prioritaria</StatusBadge>}
              preview={complaint.feedback_comment || 'Sin comentario'}
              timestamp={formatDate(complaint.handoff_created_at || complaint.updated_at)}
            />
          ))}
        </>
      ) : null}

      {inboxFilter === 'all' ? (
        <>
          {conversations.length === 0 ? (
            <p className="hint">No hay conversaciones para este tenant.</p>
          ) : null}
          {sortConversations(conversations).map((conversation) => {
            const meta = parseMeta(conversation.metadata);
            const selfServiceFlow = meta?.self_service?.flow;
            const urgencyLevel = meta?.qualification?.urgency_level;
            const isUrgent = ['emergency', 'high'].includes(urgencyLevel);
            return (
              <ConversationListItem
                key={conversation.id}
                data-urgent={isUrgent ? urgencyLevel : undefined}
                selected={conversation.id === selectedConversationId}
                onSelect={() => onSelectConversation(conversation.id)}
                title={conversation.contact_label || conversation.contact_id}
                statusText={statusLabel(conversation.status)}
                tags={conversation.contact_tags || []}
                preview={conversation.latest_message_text || 'Sin mensajes aún'}
                timestamp={formatDate(conversation.latest_message_at || conversation.updated_at)}
                badges={(
                  <>
                    {isUrgent ? (
                      <StatusBadge
                        tone="danger"
                        title={`Caso urgente (${urgencyLevel}) — atender primero`}
                      >
                        🚨 Urgente
                      </StatusBadge>
                    ) : null}
                    {conversation.current_intent ? (
                      <StatusBadge tone="neutral" title="Intención detectada">
                        {conversation.current_intent}
                      </StatusBadge>
                    ) : null}
                    {selfServiceFlow ? (
                      <StatusBadge
                        tone="accent"
                        title={`Cita ${selfServiceFlow === 'cancel' ? 'cancelada' : 'reagendada'} por el bot (self-service)`}
                      >
                        self-service
                      </StatusBadge>
                    ) : null}
                  </>
                )}
              />
            );
          })}
        </>
      ) : null}
    </aside>
  );
}
