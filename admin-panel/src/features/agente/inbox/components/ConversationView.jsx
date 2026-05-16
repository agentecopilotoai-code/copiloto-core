import { parseMeta, formatDate, messageLabel, deliveryLabel, statusLabel } from '../inboxData.js';
import { MessageContent } from './MessageContent.jsx';
import styles from '../OperationsDesk.module.css';

/**
 * ConversationView — the active conversation: detail header, the bot's
 * pre-booking qualification answers, the handoff state-machine panel and the
 * message thread (with media + interactive rendering). The composer and the
 * contact side panel are rendered alongside by the `OperationsDesk`
 * orchestrator. Every label, the handoff-button gating and the qualification
 * parsing are ported verbatim from the legacy module.
 *
 * @param {object} props
 * @param {object|null} props.selectedConversation
 * @param {object|null} props.conversationDetail
 * @param {string} props.handoffReason
 * @param {boolean} props.isBusy
 * @param {object} props.session
 * @param {string|undefined} props.tenantId
 * @param {object} props.messageThreadRef
 * @param {(reason: string) => void} props.onHandoffReasonChange
 * @param {() => void} props.onCreateHandoff
 * @param {() => void} props.onAcceptHandoff
 * @param {() => void} props.onReleaseHandoff
 * @param {() => void} [props.onMobileBack] — UI-016.8-FU: back navigation
 *   desde el detalle a la lista en mobile. Si está presente, se renderiza
 *   el botón "← Volver" (oculto en desktop vía CSS).
 * @param {React.ReactNode} props.contactPanel — slot rendered before the thread
 * @param {React.ReactNode} props.composer — slot rendered after the thread
 */
export function ConversationView({
  selectedConversation,
  conversationDetail,
  handoffReason,
  isBusy,
  session,
  tenantId,
  messageThreadRef,
  onHandoffReasonChange,
  onCreateHandoff,
  onAcceptHandoff,
  onReleaseHandoff,
  onMobileBack,
  contactPanel,
  composer,
}) {
  if (!selectedConversation) {
    return (
      <section className="conversation-detail">
        <div className="empty-detail">
          <h3>Selecciona una conversación</h3>
          <p className="hint">
            El detalle mostrará mensajes, handoffs activos y acciones operativas.
          </p>
        </div>
      </section>
    );
  }

  const meta = parseMeta(conversationDetail?.metadata);
  const qualification = meta?.qualification;
  const answered = qualification?.answered;
  const qualificationEntries = answered && typeof answered === 'object'
    ? Object.entries(answered)
    : [];
  const currentIntent = conversationDetail?.current_intent || selectedConversation.current_intent;

  return (
    <section className="conversation-detail">
      {/* UI-016.8-FU: back button mobile. CSS `.mobileBackButton` lo oculta
          en desktop (display: none) y lo muestra en una fila propia arriba
          del header a < 480px. Aria-label explícito porque el icono ← solo
          es decorativo. */}
      {onMobileBack ? (
        <button
          type="button"
          className={styles.mobileBackButton}
          aria-label="Volver a la lista de conversaciones"
          onClick={onMobileBack}
        >
          ← Volver a la lista
        </button>
      ) : null}
      <div className="detail-header">
        <div>
          <p className="eyebrow">Conversación</p>
          <h3>{conversationDetail?.contact_label || selectedConversation.contact_label}</h3>
          <p className="hint">{selectedConversation.id}</p>
        </div>
        <div className={styles.detailHeaderBadges}>
          <span className={`status-pill status-${selectedConversation.status}`}>
            {statusLabel(selectedConversation.status)}
          </span>
          {currentIntent ? (
            <span
              className={`status-pill ${styles.intentPill}`}
              title="Intención detectada por el clasificador"
            >
              {currentIntent}
            </span>
          ) : null}
        </div>
      </div>

      {qualificationEntries.length ? (
        <div className="handoff-panel" aria-label="Respuestas de calificación">
          <div>
            <strong>Calificación previa</strong>
            <p className="hint">Respuestas capturadas por el bot antes del booking.</p>
          </div>
          <ul className={styles.qualificationList}>
            {qualificationEntries.map(([qid, value]) => {
              let display = String(value);
              if (value === true) display = 'Sí';
              else if (value === false) display = 'No';
              else if (Array.isArray(value)) display = value.join(', ');
              return (
                <li key={qid} className={styles.qualificationItem}>
                  <code className={styles.qualificationCode}>{qid.slice(0, 8)}</code>
                  : <strong>{display}</strong>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      <div className="handoff-panel">
        <div>
          <strong>Handoff humano</strong>
          <p className="hint">
            Crea, acepta o libera la conversación al bot con auditoría operacional.
          </p>
        </div>
        <input
          aria-label="Razón de handoff"
          onChange={(event) => onHandoffReasonChange(event.target.value)}
          value={handoffReason}
        />
        <div className="action-row">
          <button
            className="secondary-action"
            disabled={isBusy}
            onClick={onCreateHandoff}
            type="button"
          >
            Crear handoff
          </button>
          <button
            className="primary-action"
            disabled={
              isBusy
              || !['human_required', 'waiting_agent', 'open'].includes(selectedConversation.status)
            }
            onClick={onAcceptHandoff}
            type="button"
          >
            Tomar conversación
          </button>
          <button
            className="secondary-action"
            disabled={isBusy}
            onClick={onReleaseHandoff}
            type="button"
          >
            Liberar al bot
          </button>
        </div>
      </div>

      {contactPanel}

      <div className="message-thread" aria-live="polite" ref={messageThreadRef}>
        {(conversationDetail?.messages || []).map((message) => {
          const renderableMessage = { ...message, _session: session, _tenantId: tenantId };
          return (
            <article className={`message-bubble ${message.direction}`} key={message.id}>
              <small>
                {message.sender_actor_type} · {messageLabel(message)} ·{' '}
                {formatDate(message.created_at)} · {deliveryLabel(message)}
              </small>
              <MessageContent message={renderableMessage} />
            </article>
          );
        })}
      </div>

      {composer}
    </section>
  );
}
