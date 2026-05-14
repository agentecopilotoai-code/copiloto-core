import { TagPill } from './TagPill.jsx';
import styles from './ConversationListItem.module.css';

/**
 * ConversationListItem — item de la lista del inbox operativo.
 *
 * No hace fetch ni conoce la forma del API: recibe campos ya formateados.
 * Los badges extra (urgente, intención, self-service) se pasan por el slot
 * `badges` para mantener el componente genérico.
 *
 * @param {Object} props
 * @param {React.ReactNode} props.title Nombre / etiqueta del contacto.
 * @param {React.ReactNode} [props.statusText] Texto de estado de la conversación.
 * @param {React.ReactNode} [props.badges] Badges adicionales (slot).
 * @param {Array<{id?: string, name: string, color?: string}>} [props.tags=[]]
 * @param {React.ReactNode} [props.preview] Último mensaje / comentario.
 * @param {React.ReactNode} [props.timestamp] Marca temporal ya formateada.
 * @param {boolean} [props.selected=false]
 * @param {() => void} props.onSelect
 */
export function ConversationListItem({
  title,
  statusText,
  badges = null,
  tags = [],
  preview,
  timestamp,
  selected = false,
  onSelect,
  ...rest
}) {
  return (
    <button
      type="button"
      className={[styles.card, selected ? styles['card--active'] : ''].filter(Boolean).join(' ')}
      onClick={onSelect}
      aria-pressed={selected}
      {...rest}
    >
      <span className={styles.title}>{title}</span>
      {statusText || badges ? (
        <div className={styles.row}>
          {statusText ? <span className={styles.status}>{statusText}</span> : null}
          {badges}
        </div>
      ) : null}
      {tags.length ? (
        <div className={styles.tags}>
          {tags.map((tag) => (
            <TagPill key={tag.id} tag={tag} size="sm" />
          ))}
        </div>
      ) : null}
      {preview ? <small className={styles.preview}>{preview}</small> : null}
      {timestamp ? <time className={styles.time}>{timestamp}</time> : null}
    </button>
  );
}
