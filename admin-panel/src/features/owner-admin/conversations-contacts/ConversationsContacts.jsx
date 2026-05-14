import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { ContactsList } from './components/ContactsList.jsx';
import { ContactDrawer } from './components/ContactDrawer.jsx';
import { useContactsData } from './hooks/useContactsData.js';
import styles from './ConversationsContacts.module.css';

const NOTICE_TONE = { success: 'success', error: 'danger', info: 'info', warning: 'warning' };

/**
 * UI-007.3 — Conversaciones · Contactos.
 *
 * Split of the legacy 685-LOC `ContactsModule` into a list + drawer layout:
 * `ContactsList` (search/filter + contact list) and `ContactDrawer` (detail),
 * the drawer itself composed of `ContactTagsPanel`, `ContactPackagesPanel`,
 * `ContactTimeline` and `ContactNotesPanel`. All CRM state and the mutation
 * handlers live in the `useContactsData` hook; the components stay
 * presentational. Logic is preserved verbatim from the legacy module.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/11 _ Conversaciones _ Contactos.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function ConversationsContacts({ module, session, tenant }) {
  const { profile: userProfile } = useTenantContext();
  const permissions = usePermissions({ profile: userProfile, tenant });
  const { state, actions } = useContactsData({ session, tenantId: tenant?.id });

  return (
    <RequirePermission permissions={permissions} capability="contacts.view" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Conversaciones · CRM"
          title={module?.label || 'Contactos'}
          description="CRM unificado de los canales WhatsApp, Instagram, Messenger y Web. Cada contacto tiene historial, etiquetas, paquetes, notas y estado de consentimiento."
        />

        {state.notice ? (
          <AlertBanner
            tone={NOTICE_TONE[state.notice.type] || 'info'}
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissNotice}
              >
                Cerrar
              </button>
            }
          />
        ) : null}

        {!tenant?.id ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver y gestionar sus contactos."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <ContactsList
              contacts={state.contacts}
              availableTags={state.availableTags}
              searchTerm={state.searchTerm}
              filterTagId={state.filterTagId}
              selectedContactId={state.selectedContactId}
              isBusy={state.isBusy}
              onSearchTermChange={actions.setSearchTerm}
              onFilterTagChange={actions.setFilterTagId}
              onSearch={actions.search}
              onSelect={actions.selectContact}
            />
            <ContactDrawer
              profile={state.profile}
              consent={state.consent}
              unassignedTags={state.unassignedTags}
              contactPackages={state.contactPackages}
              availablePackages={state.availablePackages}
              isBusy={state.isBusy}
              actions={actions}
            />
          </div>
        )}
      </section>
    </RequirePermission>
  );
}
