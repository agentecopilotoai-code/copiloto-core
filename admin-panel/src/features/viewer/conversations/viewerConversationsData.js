/**
 * UI-010.4 — Lectura · Conversaciones (Viewer): pure data helpers.
 *
 * El feature es una vista read-only que reusa `InboxList` (UI-009.1) y la capa
 * de datos `useInboxData` verbatim. Estos helpers cubren las únicas derivaciones
 * propias del Viewer: conteos agregados por estado / handoff para describir la
 * cadencia en el `PageHeader` sin reformular nada de la lista. Reusa
 * `parseMeta` / `isUrgentConversation` de `inboxData.js` (no duplica).
 *
 * Cero fetch, cero React — todo unit-testable sin red ni DOM.
 */

import { isUrgentConversation, parseMeta } from '../../agente/inbox/inboxData.js';

/** Descripción del PageHeader — surface el banner read-only y el contrato. */
export const CONVERSATIONS_DESCRIPTION =
  'Conversaciones activas del tenant en modo solo lectura. Filtra por «Todas» o «Quejas»; los Viewers no pueden iniciar conversaciones, tomar handoff ni enviar mensajes.';

/** Conjunto de estados de conversación considerados con handoff abierto. */
const HANDOFF_STATUSES = new Set(['human_required', 'human_active', 'waiting_agent']);

/**
 * Cuenta conversaciones por estado canónico (`open`, `human_required`,
 * `human_active`, `waiting_agent`, `waiting_user`). Devuelve un objeto con
 * cada estado encontrado en la lista; estados ausentes no aparecen como `0`
 * (evita asumir el universo cerrado).
 *
 * @param {object[]} conversations
 * @returns {Record<string, number>}
 */
export function countByStatus(conversations) {
  if (!Array.isArray(conversations)) return {};
  return conversations.reduce((acc, conversation) => {
    const status = conversation?.status;
    if (!status) return acc;
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});
}

/**
 * Cuenta cuántas conversaciones están en algún estado de handoff humano
 * (`human_required` / `human_active` / `waiting_agent`).
 *
 * @param {object[]} conversations
 * @returns {number}
 */
export function countWithHandoff(conversations) {
  if (!Array.isArray(conversations)) return 0;
  return conversations.filter((c) => HANDOFF_STATUSES.has(c?.status)).length;
}

/**
 * Cuenta conversaciones marcadas como urgentes por el bot
 * (`metadata.qualification.urgency_level` ∈ {emergency, high}). Reusa
 * `isUrgentConversation` de `inboxData.js` para que la regla quede en un solo
 * lugar.
 *
 * @param {object[]} conversations
 * @returns {number}
 */
export function countUrgent(conversations) {
  if (!Array.isArray(conversations)) return 0;
  return conversations.filter(isUrgentConversation).length;
}

/**
 * Resumen agregado de la lista — usado en el `PageHeader` para que el Viewer
 * vea el contexto sin abrir cada fila. No incluye totales que requieran un
 * endpoint adicional (SLA, tiempo medio, etc.) — sólo lo que `listConversations`
 * ya provee.
 *
 * @param {object[]} conversations
 * @param {object[]} complaints
 * @returns {{ total: number, withHandoff: number, urgent: number, complaints: number }}
 */
export function summarizeConversations(conversations, complaints) {
  const list = Array.isArray(conversations) ? conversations : [];
  const complaintList = Array.isArray(complaints) ? complaints : [];
  return {
    total: list.length,
    withHandoff: countWithHandoff(list),
    urgent: countUrgent(list),
    complaints: complaintList.length,
  };
}

// Re-export para facilitar el consumo del helper desde el orquestador sin
// abrir el barrel del inbox.
export { parseMeta };
