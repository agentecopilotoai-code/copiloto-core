/**
 * MessageComposer — the outbound message form: response type, media id / url /
 * mime affordances and the text / caption box. Presentational; the send logic
 * lives in `useInboxData`. Ported verbatim from the legacy `OperationsDesk`.
 *
 * @param {object} props
 * @param {string} props.messageText
 * @param {object} props.messageMedia
 * @param {boolean} props.isBusy
 * @param {(text: string) => void} props.onMessageTextChange
 * @param {(media: object) => void} props.onMessageMediaChange
 * @param {(event: Event) => void} props.onSendMessage
 */
export function MessageComposer({
  messageText,
  messageMedia,
  isBusy,
  onMessageTextChange,
  onMessageMediaChange,
  onSendMessage,
}) {
  return (
    <form className="message-composer" onSubmit={onSendMessage}>
      <label>
        Tipo de respuesta
        <select
          onChange={(event) => onMessageMediaChange({ ...messageMedia, type: event.target.value })}
          value={messageMedia.type}
        >
          <option value="text">Texto</option>
          <option value="image">Imagen</option>
          <option value="video">Video</option>
          <option value="audio">Audio</option>
        </select>
      </label>
      <label>
        Media ID Meta
        <input
          onChange={(event) => onMessageMediaChange({ ...messageMedia, mediaId: event.target.value })}
          placeholder="ID del media subido a WhatsApp"
          value={messageMedia.mediaId}
        />
      </label>
      <label>
        URL pública media
        <input
          onChange={(event) =>
            onMessageMediaChange({ ...messageMedia, mediaUrl: event.target.value })}
          placeholder="https://..."
          value={messageMedia.mediaUrl}
        />
      </label>
      <label>
        MIME type
        <input
          onChange={(event) =>
            onMessageMediaChange({ ...messageMedia, mimeType: event.target.value })}
          placeholder="image/jpeg, video/mp4, audio/ogg"
          value={messageMedia.mimeType}
        />
      </label>
      <label>
        Respuesta outbound / caption
        <textarea
          onChange={(event) => onMessageTextChange(event.target.value)}
          placeholder="Escribe texto o caption para imagen/video..."
          value={messageText}
        />
      </label>
      <button
        className="primary-action"
        disabled={isBusy || (messageMedia.type === 'text' && !messageText.trim())}
        type="submit"
      >
        Enviar respuesta
      </button>
    </form>
  );
}
