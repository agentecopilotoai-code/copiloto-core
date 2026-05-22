import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { useInboxData } from './hooks/useInboxData.js';
import { useContactPanelData } from './hooks/useContactPanelData.js';
import { useScheduleData } from './hooks/useScheduleData.js';
import { useServiceRequestsData } from './hooks/useServiceRequestsData.js';
import { InboxList } from './components/InboxList.jsx';
import { ConversationView } from './components/ConversationView.jsx';
import { MessageComposer } from './components/MessageComposer.jsx';
import { ContactSidePanel } from './components/ContactSidePanel.jsx';
import { formatDate } from './inboxData.js';

/**
 * UI-009.1 — Operación · Inbox (Agente).
 *
 * Structural split of the legacy monolithic `OperationsDesk` (2088 LOC) into a
 * feature directory: this orchestrator + `useInboxData` / `useContactPanelData`
 * hooks + pure `inboxData.js` + the `InboxList` / `ConversationView` /
 * `MessageComposer` / `ContactSidePanel` components (the side panel further
 * split into `contact-panel/` sub-sections). Every `coreApi` call, the
 * WebSocket live-refresh stream + exponential-backoff reconnect, the handoff
 * state machine, the optimistic conversation-detail set and all `data-*`
 * attributes are preserved verbatim — this is a refactor, not a rewrite.
 *
 * Gated by `conversations.view` (mode R) via `<RequirePermission>`; the backend
 * remains the authority. The module id stays `operations-desk` for routing
 * stability — the feature folder is `agente/inbox/`, so the agent's home
 * `operations-desk` now renders this Inbox view.
 *
 * Visual reference: `docs/HTML DESIGN/Agente/28 _ Operación · Inbox.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
// BUG-103: outer component que GATEA por permisos ANTES de montar el body
// que dispara `useInboxData` (lista conversaciones + abre WebSocket de
// live-refresh) y los hooks de contact/schedule/service-requests. Sin
// esta separación, viewers/agents sin `conversations.view` triggereaban
// TODAS las network calls y el WS antes de ver el AccessDenied.
export function OperationsDesk(props) {
  const { tenant } = props;
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  return (
    <RequirePermission permissions={permissions} capability="conversations.view">
      <OperationsDeskBody {...props} />
    </RequirePermission>
  );
}

function OperationsDeskBody({ module, session, tenant }) {
  const { state, actions } = useInboxData({ session, tenant });
  const contact = useContactPanelData({
    session,
    tenant,
    conversationDetail: state.conversationDetail,
    setNotice: actions.setNotice,
    refreshConversations: actions.refreshConversations,
    refreshDetail: actions.refreshDetail,
  });
  const schedule = useScheduleData({
    session,
    tenant,
    conversationDetail: state.conversationDetail,
    selectedConversationId: state.selectedConversationId,
    setNotice: actions.setNotice,
  });
  const serviceRequests = useServiceRequestsData({
    session,
    tenant,
    conversationDetail: state.conversationDetail,
    selectedConversationId: state.selectedConversationId,
    setNotice: actions.setNotice,
  });

  // The notice setter is shared across every hook, so `useInboxData`'s
  // `notice` is the single source of truth for the banner.
  const { notice } = state;
  const isBusy = state.isBusy
    || contact.state.isBusy
    || schedule.state.isBusy
    || serviceRequests.state.isBusy;

  // El gate de permisos ya lo hizo OperationsDesk outer; aquí solo renderizamos.
  return (
    <>
      <section className="module-card operations-desk">
        <div className="module-heading">
          <div>
            <p className="eyebrow">{module.label}</p>
            <h2>Inbox operativo</h2>
            <p className="hint">{module.summary}</p>
          </div>
          <div className="live-refresh-status">
            <span>
              Tiempo real WebSocket:{' '}
              {state.streamStatus === 'connected' ? 'conectado' : state.streamStatus}
            </span>
            {state.lastLiveRefreshAt
              ? <small>Último evento: {formatDate(state.lastLiveRefreshAt)}</small>
              : <small>Esperando cambios del servidor</small>}
            <button
              className="secondary-action"
              disabled={isBusy}
              onClick={() => actions.refreshConversations(true)}
              type="button"
            >
              Refrescar inbox
            </button>
          </div>
        </div>

        {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

        {/* UI-016.8-FU — `data-mobile-view` lo consume `OperationsDesk.module.css`
            para mostrar SOLO la lista o SOLO el detalle a < 480px. En desktop
            el CSS ignora el atributo y se muestra el side-by-side normal. */}
        <div className="operations-layout" data-mobile-view={state.mobileView}>
          <InboxList
            conversations={state.conversations}
            complaints={state.complaints}
            inboxFilter={state.inboxFilter}
            selectedConversationId={state.selectedConversationId}
            startForm={state.startForm}
            isBusy={isBusy}
            onFilterChange={actions.setInboxFilter}
            onSelectConversation={actions.selectConversation}
            onStartFormChange={actions.setStartForm}
            onStartConversation={actions.handleStartConversation}
          />

          <ConversationView
            selectedConversation={state.selectedConversation}
            conversationDetail={state.conversationDetail}
            handoffReason={state.handoffReason}
            isBusy={isBusy}
            session={session}
            tenantId={tenant?.id}
            messageThreadRef={state.messageThreadRef}
            onHandoffReasonChange={actions.setHandoffReason}
            onCreateHandoff={actions.createHandoff}
            onAcceptHandoff={actions.acceptHandoff}
            onReleaseHandoff={actions.releaseHandoff}
            onMobileBack={actions.showMobileList}
            contactPanel={(
              <ContactSidePanel
                contact={contact}
                schedule={schedule}
                serviceRequests={serviceRequests}
                conversationDetail={state.conversationDetail}
                selectedConversation={state.selectedConversation}
              />
            )}
            composer={(
              <MessageComposer
                messageText={state.messageText}
                messageMedia={state.messageMedia}
                isBusy={isBusy}
                onMessageTextChange={actions.setMessageText}
                onMessageMediaChange={actions.setMessageMedia}
                onSendMessage={actions.handleSendMessage}
              />
            )}
          />
        </div>
      </section>
    </>
  );
}
