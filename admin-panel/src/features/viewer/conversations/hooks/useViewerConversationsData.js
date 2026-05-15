import { useMemo } from 'react';

import { useInboxData } from '../../../agente/inbox/index.js';
import { summarizeConversations } from '../viewerConversationsData.js';

/**
 * UI-010.4 — capa de datos de «Lectura · Conversaciones» (Viewer).
 *
 * Wrapper fino sobre `useInboxData`: NO re-consulta nada — reusa verbatim la
 * lista de conversaciones, la lista de quejas, el filtro de inbox y el stream
 * WebSocket de tiempo real del Inbox de Agente. **Expone solo la rebanada
 * read-only**: ni el formulario «iniciar conversación», ni el estado del
 * composer, ni las acciones de handoff (`acceptHandoff` / `releaseHandoff` /
 * `createHandoff`) — los Viewers no obtienen ningún CTA de escritura (criterio
 * global UI-010 — «100% de las acciones write deben estar ocultas»).
 *
 * Reusa además el helper puro `summarizeConversations` para derivar conteos
 * agregados (total, con handoff, urgentes, quejas) que el `PageHeader` puede
 * pintar sin reformular la lista.
 *
 * @param {object} options
 * @param {object} options.session — sesión admin (lleva el access token)
 * @param {object|undefined} options.tenant — tenant activo
 * @returns {{ state: object, actions: object }}
 */
export function useViewerConversationsData({ session, tenant }) {
  const { state: inboxState, actions: inboxActions } = useInboxData({ session, tenant });

  const summary = useMemo(
    () => summarizeConversations(inboxState.conversations, inboxState.complaints),
    [inboxState.conversations, inboxState.complaints],
  );

  return {
    state: {
      tenantId: inboxState.tenantId,
      conversations: inboxState.conversations,
      complaints: inboxState.complaints,
      inboxFilter: inboxState.inboxFilter,
      summary,
    },
    actions: {
      // Único setter expuesto: el filtro `Todas` / `Quejas` es read-only por
      // diseño (alterna qué subconjunto se pinta; no muta nada en el servidor).
      setInboxFilter: inboxActions.setInboxFilter,
    },
  };
}
