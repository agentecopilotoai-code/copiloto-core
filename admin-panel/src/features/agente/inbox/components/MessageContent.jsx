import { interactivePayload, interactiveSelection, mediaSource } from '../inboxData.js';

/**
 * Message-content renderers for the conversation thread. Extracted verbatim
 * from the legacy `OperationsDesk` — handles text, image/video/audio media and
 * inbound/outbound WhatsApp interactive (button + list) messages. Presentation
 * only; no fetch, no state.
 */

function renderInteractiveOutbound(interactive, message) {
  const body = interactive?.body?.text || message?.body_text || '';
  const header = interactive?.header?.text;
  const footer = interactive?.footer?.text;
  if (interactive?.type === 'button') {
    const buttons = interactive?.action?.buttons || [];
    return (
      <div className="message-interactive">
        {header ? <p className="interactive-header"><strong>{header}</strong></p> : null}
        {body ? <p>{body}</p> : null}
        <div className="interactive-buttons">
          {buttons.map((button, index) => (
            <span className="interactive-chip" key={button?.reply?.id || index}>
              {button?.reply?.title || 'Opción'}
            </span>
          ))}
        </div>
        {footer ? <p className="interactive-footer">{footer}</p> : null}
      </div>
    );
  }
  if (interactive?.type === 'list') {
    const sections = interactive?.action?.sections || [];
    const buttonLabel = interactive?.action?.button;
    return (
      <div className="message-interactive">
        {header ? <p className="interactive-header"><strong>{header}</strong></p> : null}
        {body ? <p>{body}</p> : null}
        {sections.map((section, sectionIndex) => (
          <div className="interactive-section" key={section?.title || sectionIndex}>
            {section?.title ? <p className="interactive-section-title">{section.title}</p> : null}
            <div className="interactive-buttons">
              {(section.rows || []).map((row, rowIndex) => (
                <span className="interactive-chip" key={row?.id || `${sectionIndex}-${rowIndex}`}>
                  {row?.title || 'Opción'}
                  {row?.description ? <small> · {row.description}</small> : null}
                </span>
              ))}
            </div>
          </div>
        ))}
        {buttonLabel ? <p className="interactive-cta"><em>Botón: {buttonLabel}</em></p> : null}
        {footer ? <p className="interactive-footer">{footer}</p> : null}
      </div>
    );
  }
  return body ? <p>{body}</p> : <p><em>Mensaje interactivo</em></p>;
}

function renderInteractiveInbound(selection, message) {
  return (
    <div className="message-interactive">
      <p>
        <em>El cliente seleccionó: </em>
        <span className="interactive-chip interactive-chip-selected">{selection.title}</span>
      </p>
      {selection.description ? <p><small>{selection.description}</small></p> : null}
      {message?.body_text && message.body_text !== selection.title ? (
        <p>{message.body_text}</p>
      ) : null}
    </div>
  );
}

/**
 * Render a single message's body: media, interactive or plain text.
 *
 * @param {object} message — the message record (with `_session` / `_tenantId`).
 * @param {object} [session] — admin session (defaults to `message._session`).
 * @param {string} [tenantId] — active tenant id (defaults to `message._tenantId`).
 */
export function MessageContent({
  message,
  session = message._session,
  tenantId = message._tenantId,
}) {
  const source = mediaSource(message, session, tenantId);
  const text = message.body_text;

  if (message.message_type === 'image') {
    return (
      <div className="message-media">
        {source
          ? <img alt={text || 'Imagen de WhatsApp'} src={source} />
          : <span>Imagen · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  if (message.message_type === 'video') {
    return (
      <div className="message-media">
        {source
          ? <video controls src={source}>Tu navegador no soporta video embebido.</video>
          : <span>Video · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  if (message.message_type === 'audio') {
    return (
      <div className="message-media">
        {source
          ? <audio controls src={source}>Tu navegador no soporta audio embebido.</audio>
          : <span>Audio · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  if (message.message_type === 'interactive') {
    const inboundSelection = message.direction === 'inbound' ? interactiveSelection(message) : null;
    if (inboundSelection) {
      return renderInteractiveInbound(inboundSelection, message);
    }
    const interactive = interactivePayload(message);
    if (interactive) {
      return renderInteractiveOutbound(interactive, message);
    }
  }

  return <p>{text || JSON.stringify(message.payload)}</p>;
}
