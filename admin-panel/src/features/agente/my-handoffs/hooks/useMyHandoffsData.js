import { useMemo, useState } from 'react';

import { useInboxData } from '../../inbox/index.js';
import {
  DEFAULT_HANDOFF_FILTER,
  applyHandoffFilter,
  deriveHandoffCounts,
} from '../myHandoffsData.js';

/**
 * UI-009.2 — capa de datos de «Mis handoffs».
 *
 * Wrapper fino sobre `useInboxData`: NO re-consulta nada — reusa verbatim la
 * lista de conversaciones, el stream WebSocket de tiempo real y las acciones de
 * handoff (`acceptHandoff` / `releaseHandoff`) del Inbox. Encima añade sólo:
 *   1. la resolución del id del usuario actual (para el filtro «Mías»),
 *   2. el estado de la tab de filtro de la cola de handoffs,
 *   3. la lista derivada ya filtrada + los conteos por tab.
 *
 * El id del usuario actual se resuelve desde `profile.sub` (el subject de
 * Auth0) — es el único identificador del agente disponible en el frontend. El
 * filtro de «mis handoffs» se compara contra `active_handoff_assigned_to` de
 * cada conversación; ese campo lo escribe el backend al aceptar un handoff.
 *
 * @param {object} options
 * @param {object} options.session — sesión admin (lleva el access token)
 * @param {object|undefined} options.tenant — tenant activo
 * @param {object|undefined} options.profile — perfil del usuario autenticado
 * @returns {{ state: object, actions: object }}
 */
export function useMyHandoffsData({ session, tenant, profile }) {
  const { state: inboxState, actions: inboxActions } = useInboxData({ session, tenant });
  const [handoffFilter, setHandoffFilter] = useState(DEFAULT_HANDOFF_FILTER);

  const currentUserId = profile?.sub || null;

  const counts = useMemo(
    () => deriveHandoffCounts(inboxState.conversations, currentUserId),
    [inboxState.conversations, currentUserId],
  );

  const handoffs = useMemo(
    () => applyHandoffFilter(inboxState.conversations, handoffFilter, currentUserId),
    [inboxState.conversations, handoffFilter, currentUserId],
  );

  return {
    state: {
      tenantId: inboxState.tenantId,
      conversations: inboxState.conversations,
      handoffs,
      counts,
      handoffFilter,
      currentUserId,
      selectedConversationId: inboxState.selectedConversationId,
      selectedConversation: inboxState.selectedConversation,
      isBusy: inboxState.isBusy,
      notice: inboxState.notice,
      lastLiveRefreshAt: inboxState.lastLiveRefreshAt,
      streamStatus: inboxState.streamStatus,
    },
    actions: {
      setHandoffFilter,
      setSelectedConversationId: inboxActions.setSelectedConversationId,
      dismissNotice: inboxActions.dismissNotice,
      refreshConversations: inboxActions.refreshConversations,
      // Acciones de handoff reusadas verbatim del Inbox.
      acceptHandoff: inboxActions.acceptHandoff,
      releaseHandoff: inboxActions.releaseHandoff,
    },
  };
}
