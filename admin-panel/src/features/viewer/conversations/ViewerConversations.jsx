import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { InboxList } from '../../agente/inbox/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { useViewerConversationsData } from './hooks/useViewerConversationsData.js';
import { CONVERSATIONS_DESCRIPTION } from './viewerConversationsData.js';
import styles from './ViewerConversations.module.css';

/**
 * UI-010.4 — Viewer · Lectura · Conversaciones.
 *
 * Cuarta y última vista del rol Viewer. Reusa `InboxList` (UI-009.1) en modo
 * read-only — el composer, las acciones de handoff y el formulario «iniciar
 * conversación» no se renderizan. El nuevo prop `showStartForm={false}` (añadido
 * en el mismo PR sin cambiar el default `true` que usa `OperationsDesk`) oculta
 * el formulario de write que normalmente encabeza la lista.
 *
 * Gateada por `<RequirePermission capability="conversations.view" mode="R">` —
 * la misma capability que el Inbox de Agente; el backend reverifica con JWT +
 * RLS. El `ReadOnlyShell` (UI-002) ya añade el banner permanente «Modo solo
 * lectura». No se renderizan `ConversationView` / `MessageComposer` /
 * `ContactSidePanel`: los Viewers ven sólo la lista de conversaciones con sus
 * `ConversationListItem` (badges + preview + timestamp), suficiente para
 * cumplir el spec del backlog («Reusa `InboxList` en modo read-only — composer
 * oculto, CTAs handoff desactivados»).
 *
 * Referencia visual: `docs/HTML DESIGN/Viewer/36 _ Lectura _ Conversaciones.html`.
 * Diferencias intencionales declaradas: el HTML muestra (a) una columna
 * derecha con el detalle del mensaje + thread, (b) chips de SLA por fila y
 * (c) CTAs «Tomar handoff» / «Liberar» por fila. Esos elementos exigen montar
 * el `ConversationView` (que arrastra el `MessageComposer` con write actions)
 * y/o las acciones de handoff, que están explícitamente prohibidas por el
 * criterio global UI-010 («100% de las acciones write deben estar ocultas»).
 * Se difieren — no se inventan datos ni se cablea CTAs de escritura.
 *
 * @param {{ module?: object, session: object, tenant: object }} props
 */
export function ViewerConversations({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useViewerConversationsData({ session, tenant });

  const hasTenant = Boolean(state.tenantId);

  return (
    <RequirePermission permissions={permissions} capability="conversations.view" mode="R">
      <section className={styles.page} data-module="viewer-conversations">
        <PageHeader
          eyebrow="Lectura"
          title={module?.label || 'Conversaciones'}
          description={CONVERSATIONS_DESCRIPTION}
          actions={
            hasTenant ? (
              <span className={styles.summaryChip} aria-label="Resumen del inbox">
                {state.summary.total} conversaciones · {state.summary.withHandoff} con handoff
              </span>
            ) : null
          }
        />

        {!hasTenant ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver sus conversaciones."
            />
          </Card>
        ) : (
          <InboxList
            conversations={state.conversations}
            complaints={state.complaints}
            inboxFilter={state.inboxFilter}
            selectedConversationId={null}
            showStartForm={false}
            onFilterChange={actions.setInboxFilter}
            onSelectConversation={() => {}}
          />
        )}
      </section>
    </RequirePermission>
  );
}
