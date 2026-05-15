/**
 * UI-009.2 — Operación · Mis handoffs (Agente): helpers puros.
 *
 * El backlog manda «filtro pre-aplicado `assignee_id = current_user`, reusa
 * `InboxList`». Esta vista no re-consulta nada: corre sobre la misma respuesta
 * tenant-scoped de `listConversations` que ya posee `useInboxData`, y filtra en
 * cliente por el handoff activo de cada conversación.
 *
 * El endpoint `GET /conversations` expone, por cada fila, el handoff abierto /
 * aceptado más reciente como `active_handoff_id` / `active_handoff_status` /
 * `active_handoff_assigned_to` (ver `app/api/v1/routes.py::list_conversations`).
 * `active_handoff_assigned_to` es el `app.users.id` que aceptó el handoff —
 * el mismo id que `current_user_id_from_request` graba en `handoffs.assigned_to`.
 *
 * Helpers puros, sin React ni red — unit-testables en aislamiento. Reusa los
 * formatters de `inboxData.js` (cero duplicación).
 */

import { formatDate, statusLabel } from '../inbox/inboxData.js';

/** Estados de conversación que implican una escalada a humano pendiente/activa. */
const HANDOFF_STATUSES = Object.freeze(['human_required', 'waiting_agent', 'human_active']);

/**
 * Definición de las tabs del filtro de cola de handoffs. El HTML de referencia
 * muestra `Todos / Sin asignar / Mías / Colegas / Cerrados`; sólo se exponen las
 * que la respuesta de `listConversations` puede respaldar con datos reales:
 * `all` (todo handoff con escalada), `unassigned` (handoff sin `assigned_to`) y
 * `mine` (handoff cuyo `assigned_to` es el usuario actual). `Colegas` y
 * `Cerrados` se difieren — ver nota de diferencia intencional en docs.
 */
export const HANDOFF_FILTERS = Object.freeze([
  { id: 'all', label: 'Todos' },
  { id: 'unassigned', label: 'Sin asignar' },
  { id: 'mine', label: 'Mías' },
]);

/** El filtro por defecto: la cola completa de handoffs del tenant. */
export const DEFAULT_HANDOFF_FILTER = 'all';

/** True cuando una conversación tiene una escalada a humano abierta/aceptada. */
export function isHandoffConversation(conversation) {
  if (!conversation) return false;
  if (conversation.active_handoff_id) return true;
  return HANDOFF_STATUSES.includes(conversation.status);
}

/** Sólo las conversaciones escaladas a humano (la cola de handoffs completa). */
export function filterHandoffs(conversations) {
  if (!Array.isArray(conversations)) return [];
  return conversations.filter(isHandoffConversation);
}

/**
 * Las conversaciones escaladas que aún no tiene nadie asignado: hay handoff pero
 * `active_handoff_assigned_to` viene vacío.
 */
export function filterUnassignedHandoffs(conversations) {
  return filterHandoffs(conversations).filter(
    (conversation) => !conversation.active_handoff_assigned_to,
  );
}

/**
 * Filtro pre-aplicado de la vista: las conversaciones escaladas cuyo handoff
 * activo está asignado al agente actual (`assignee_id = current_user`).
 *
 * @param {Array<object>} conversations  lista de `listConversations`
 * @param {string|null|undefined} currentUserId  id del usuario actual
 * @returns {Array<object>}
 */
export function filterMyHandoffs(conversations, currentUserId) {
  if (!currentUserId) return [];
  return filterHandoffs(conversations).filter(
    (conversation) => conversation.active_handoff_assigned_to === currentUserId,
  );
}

/**
 * Aplica una de las tabs de `HANDOFF_FILTERS` a la lista de conversaciones.
 *
 * @param {Array<object>} conversations
 * @param {'all'|'unassigned'|'mine'} filterId
 * @param {string|null|undefined} currentUserId
 * @returns {Array<object>}
 */
export function applyHandoffFilter(conversations, filterId, currentUserId) {
  if (filterId === 'unassigned') return filterUnassignedHandoffs(conversations);
  if (filterId === 'mine') return filterMyHandoffs(conversations, currentUserId);
  return filterHandoffs(conversations);
}

/**
 * Conteos por tab para los badges del filtro: `{ all, unassigned, mine }`.
 *
 * @param {Array<object>} conversations
 * @param {string|null|undefined} currentUserId
 * @returns {{ all: number, unassigned: number, mine: number }}
 */
export function deriveHandoffCounts(conversations, currentUserId) {
  return {
    all: filterHandoffs(conversations).length,
    unassigned: filterUnassignedHandoffs(conversations).length,
    mine: filterMyHandoffs(conversations, currentUserId).length,
  };
}

/**
 * Da forma a una conversación escalada hacia la fila de la tabla de handoffs.
 * Sólo usa campos que la respuesta de `listConversations` realmente trae —
 * el tiempo de espera sale de `handoff_created_at` / `updated_at`, no de un
 * timer de SLA (que el endpoint no expone).
 *
 * @param {object} conversation
 * @param {string|null|undefined} currentUserId
 * @returns {object}
 */
export function toHandoffRow(conversation, currentUserId) {
  const assignedTo = conversation.active_handoff_assigned_to || null;
  const isMine = Boolean(currentUserId) && assignedTo === currentUserId;
  return {
    id: conversation.id,
    contactLabel: conversation.contact_label || conversation.contact_id || 'Contacto',
    statusText: statusLabel(conversation.status),
    status: conversation.status,
    intent: conversation.current_intent || null,
    waitingSince: formatDate(
      conversation.handoff_created_at || conversation.updated_at,
    ),
    assignedTo,
    isMine,
    isUnassigned: !assignedTo,
    ownership: isMine ? 'Mía' : assignedTo ? 'Colega' : 'Sin asignar',
  };
}
