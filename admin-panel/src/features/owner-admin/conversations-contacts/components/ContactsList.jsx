import { Card, EmptyState } from '../../../../components/ui/index.js';
import { ContactCard } from '../../../../components/domain/index.js';
import styles from '../ConversationsContacts.module.css';

/**
 * Left column of the Contactos view: the search + tag filter form and the
 * scrollable list of `ContactCard`s. Presentational — all state and the
 * `onSearch`/`onSelect` callbacks come from the view via the data hook.
 *
 * @param {{
 *   contacts: Array<object>,
 *   availableTags: Array<object>,
 *   searchTerm: string,
 *   filterTagId: string,
 *   selectedContactId: string|null,
 *   isBusy: boolean,
 *   onSearchTermChange: (value: string) => void,
 *   onFilterTagChange: (value: string) => void,
 *   onSearch: () => void,
 *   onSelect: (contactId: string) => void,
 * }} props
 */
export function ContactsList({
  contacts,
  availableTags,
  searchTerm,
  filterTagId,
  selectedContactId,
  isBusy,
  onSearchTermChange,
  onFilterTagChange,
  onSearch,
  onSelect,
}) {
  return (
    <Card padding="md" className={styles.listCard}>
      <form
        className={styles.filters}
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <label className={styles.filter}>
          <span className={styles.filterLabel}>Buscar</span>
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => onSearchTermChange(event.target.value)}
            placeholder="Nombre o teléfono"
            maxLength={160}
          />
        </label>
        <label className={styles.filter}>
          <span className={styles.filterLabel}>Etiqueta</span>
          <select value={filterTagId} onChange={(event) => onFilterTagChange(event.target.value)}>
            <option value="">Todas</option>
            {availableTags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className={styles.secondaryButton} disabled={isBusy}>
          Aplicar
        </button>
      </form>

      <div className={styles.contactList} aria-label="Contactos">
        {contacts.length === 0 ? (
          <EmptyState
            title="Sin contactos"
            description="Ningún contacto coincide con la búsqueda o el filtro de etiqueta."
          />
        ) : (
          contacts.map((contact) => (
            <ContactCard
              key={contact.id}
              contact={contact}
              selected={contact.id === selectedContactId}
              onSelect={() => onSelect(contact.id)}
            />
          ))
        )}
      </div>
    </Card>
  );
}
