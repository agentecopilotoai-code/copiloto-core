import { TagPill } from './TagPill.jsx';
import styles from './ContactCard.module.css';

/**
 * ContactCard — item de lista de contactos del CRM (selección en panel lateral).
 *
 * No hace fetch: recibe el contacto por props.
 *
 * @param {Object} props
 * @param {Object} props.contact Contacto con `display_name`, `phone_e164`, `wa_id`, `tags`, `appointments_count`.
 * @param {boolean} [props.selected=false]
 * @param {() => void} props.onSelect
 */
export function ContactCard({ contact, selected = false, onSelect }) {
  if (!contact) return null;
  const name = contact.display_name || contact.phone_e164 || contact.wa_id || 'Contacto';
  const tags = contact.tags || [];
  return (
    <button
      type="button"
      className={[styles.card, selected ? styles['card--active'] : ''].filter(Boolean).join(' ')}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className={styles.name}>{name}</span>
      {tags.length ? (
        <span className={styles.tags}>
          {tags.map((tag) => (
            <TagPill key={tag.id} tag={tag} size="sm" />
          ))}
        </span>
      ) : null}
      {contact.phone_e164 ? <small className={styles.meta}>{contact.phone_e164}</small> : null}
      <small className={styles.meta}>{contact.appointments_count || 0} citas</small>
    </button>
  );
}
