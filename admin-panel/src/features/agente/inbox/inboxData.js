/**
 * UI-009.1 — Operación · Inbox: pure data helpers.
 *
 * Constants, catalogues, formatters, payload builders and message-rendering
 * helpers extracted verbatim from the legacy `OperationsDesk` (2088 LOC) so the
 * `InboxList` / `ConversationView` / `MessageComposer` / `ContactSidePanel`
 * split shares them and they stay unit-testable without React. No behaviour
 * changed — every literal, label and rule is identical to the legacy module.
 */

import { conversationMessageMediaUrl } from '../../../services/coreApi.js';

/** Weekly working-day keys + Spanish labels for the resource form. */
export const WORKING_DAYS = [
  { key: 'mon', label: 'Lun' },
  { key: 'tue', label: 'Mar' },
  { key: 'wed', label: 'Mié' },
  { key: 'thu', label: 'Jue' },
  { key: 'fri', label: 'Vie' },
  { key: 'sat', label: 'Sáb' },
  { key: 'sun', label: 'Dom' },
];

/** Spanish payment-status labels for the appointment payment block. */
export const PAYMENT_LABELS = {
  not_required: 'Sin pago',
  pending: 'Pendiente',
  link_sent: 'Link enviado',
  paid: 'Pagado',
  failed: 'Fallido',
  refunded: 'Reembolsado',
};

/** Blank working-hours form: Mon-Fri enabled 09:00-18:00. */
export function emptyWorkingHoursForm() {
  return WORKING_DAYS.reduce((acc, { key }, index) => {
    acc[key] = { enabled: index < 5, start: '09:00', end: '18:00' };
    return acc;
  }, {});
}

/** Hydrate the working-hours form from a resource's `capabilities` JSON. */
export function workingHoursFromCapabilities(capabilities) {
  const config = capabilities && typeof capabilities === 'object' ? capabilities : {};
  const stored = config.working_hours && typeof config.working_hours === 'object'
    ? config.working_hours
    : {};
  return WORKING_DAYS.reduce((acc, { key }, index) => {
    const slots = Array.isArray(stored[key]) ? stored[key] : [];
    const slot = slots[0];
    acc[key] = {
      enabled: Boolean(slot),
      start: slot?.start || '09:00',
      end: slot?.end || '18:00',
      _defaultEnabled: index < 5,
    };
    return acc;
  }, {});
}

/** Serialize the working-hours form back to the `working_hours` JSON shape. */
export function workingHoursToJson(hours) {
  return WORKING_DAYS.reduce((acc, { key }) => {
    const day = hours[key];
    acc[key] = day?.enabled ? [{ start: day.start, end: day.end }] : [];
    return acc;
  }, {});
}

/** Today's date as a `YYYY-MM-DD` string (local time). */
export function todayISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

/** Format an ISO date/time for the es-CO locale; `Sin fecha` when empty. */
export function formatDate(value) {
  if (!value) return 'Sin fecha';
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

/** The Spanish label for a conversation status. */
export function statusLabel(status) {
  const labels = {
    human_active: 'Humano activo',
    human_required: 'Requiere humano',
    open: 'Bot activo',
    waiting_agent: 'Espera agente',
    waiting_user: 'Espera usuario',
  };
  return labels[status] || status;
}

/** The Spanish label for a message type. */
export function messageLabel(message) {
  const labels = {
    audio: 'Audio',
    image: 'Imagen',
    interactive: 'Interactivo',
    text: 'Texto',
    video: 'Video',
  };
  return labels[message.message_type] || message.message_type || 'Mensaje';
}

/** Human-readable delivery status for an outbound/inbound message. */
export function deliveryLabel(message) {
  if (message.status === 'queued') return 'En cola: pendiente del worker';
  if (message.status === 'failed') {
    return `Falló WhatsApp: ${message.error_message || message.error_code || 'sin detalle'}`;
  }
  if (message.payload?.provider_result?.mocked) return 'Simulado local: no salió a WhatsApp';
  if (message.external_message_id) return `Aceptado por WhatsApp: ${message.external_message_id}`;
  if (message.status === 'sent') return 'Enviado al proveedor';
  return message.status;
}

/** Parse a possibly-stringified `metadata` blob; returns `null` on bad JSON. */
export function parseMeta(raw) {
  if (typeof raw !== 'string') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** True when a conversation is flagged emergency/high urgency by the bot. */
export function isUrgentConversation(conversation) {
  const meta = parseMeta(conversation.metadata);
  return ['emergency', 'high'].includes(meta?.qualification?.urgency_level);
}

/** Stable urgency-first sort of the conversation list (urgent items float up). */
export function sortConversations(conversations) {
  return [...conversations].sort((a, b) => {
    const ua = isUrgentConversation(a) ? 1 : 0;
    const ub = isUrgentConversation(b) ? 1 : 0;
    return ub - ua;
  });
}

/** The interactive payload of a message, when present. */
export function interactivePayload(message) {
  const payload = message?.payload;
  if (!payload || typeof payload !== 'object') return null;
  if (payload.interactive && typeof payload.interactive === 'object') {
    return payload.interactive;
  }
  return null;
}

/** The inbound interactive selection (id/title) the client picked, if any. */
export function interactiveSelection(message) {
  const payload = message?.payload;
  if (!payload || typeof payload !== 'object') return null;
  const id = payload.interactive_id;
  const title = payload.interactive_title;
  if (typeof id !== 'string' || typeof title !== 'string') return null;
  return {
    id,
    title,
    type: payload.interactive_type,
    description: payload.interactive_description,
  };
}

/** Authenticated media URL for an image/video/audio message, when streamable. */
export function mediaSource(message, session, tenantId) {
  if (
    tenantId
    && message.id
    && message.conversation_id
    && message.media_id
    && ['image', 'video', 'audio'].includes(message.message_type)
  ) {
    return conversationMessageMediaUrl(session, tenantId, message.conversation_id, message.id);
  }
  return null;
}

/**
 * Merge a payment-summary response into an appointment record, keeping the
 * appointment's existing value for any field the summary omits. Extracted
 * verbatim from the legacy `applyPaymentSummary`.
 */
export function mergeAppointmentPayment(appointment, summary) {
  return {
    ...appointment,
    payment_status: summary.payment_status ?? appointment.payment_status,
    payment_amount: summary.payment_amount ?? appointment.payment_amount,
    payment_currency: summary.payment_currency ?? appointment.payment_currency,
    payment_link: summary.payment_link ?? appointment.payment_link,
    payment_provider: summary.payment_provider ?? appointment.payment_provider,
    payment_provider_reference:
      summary.payment_provider_reference ?? appointment.payment_provider_reference,
    payment_link_generated_at:
      summary.payment_link_generated_at ?? appointment.payment_link_generated_at,
    payment_link_sent_at: summary.payment_link_sent_at ?? appointment.payment_link_sent_at,
    payment_paid_at: summary.payment_paid_at ?? appointment.payment_paid_at,
  };
}

/** Subtotal + grand total for a quote item list (verbatim from legacy). */
export function computeQuoteTotals(quoteItems, quoteDiscount, quoteTax) {
  const subtotal = quoteItems.reduce(
    (acc, item) => acc + (parseFloat(item.qty) || 0) * (parseFloat(item.unit_price) || 0),
    0,
  );
  const grandTotal = subtotal - (parseFloat(quoteDiscount) || 0) + (parseFloat(quoteTax) || 0);
  return { subtotal, grandTotal };
}

/** Blank resource form for the contact panel's resource builder. */
export function emptyResourceForm(verticalCode = '') {
  return {
    code: '',
    name: '',
    resourceType: 'staff',
    verticalCode,
    workingHours: emptyWorkingHoursForm(),
    bio: '',
    photoMediaAssetId: '',
    specialty: '',
    licenseNumber: '',
    yearsOfExperience: '',
    publicProfile: true,
  };
}

/** Hydrate the resource form from an existing resource record. */
export function resourceFormFromRecord(resource, fallbackVerticalCode = '') {
  return {
    code: resource.code || '',
    name: resource.name || '',
    resourceType: resource.resource_type || 'staff',
    verticalCode: resource.vertical_code || fallbackVerticalCode || '',
    workingHours: workingHoursFromCapabilities(resource.capabilities),
    bio: resource.bio || '',
    photoMediaAssetId: resource.photo_media_asset_id || '',
    specialty: resource.specialty || '',
    licenseNumber: resource.license_number || '',
    yearsOfExperience:
      resource.years_of_experience === null || resource.years_of_experience === undefined
        ? ''
        : String(resource.years_of_experience),
    publicProfile: resource.public_profile !== false,
  };
}

/** Blank "iniciar conversación" form. */
export function emptyStartForm() {
  return {
    displayName: '',
    initialMessage: '',
    mediaId: '',
    mediaUrl: '',
    mimeType: '',
    phone: '',
    type: 'text',
  };
}

/** Blank message-composer media descriptor. */
export function emptyMessageMedia() {
  return { mediaId: '', mediaUrl: '', mimeType: '', type: 'text' };
}

/**
 * Build the `createResource` / `updateResource` payload from the resource form.
 * Preserves the legacy capabilities + profile-field shaping verbatim.
 */
export function buildResourcePayload(resourceForm) {
  const capabilities = { working_hours: workingHoursToJson(resourceForm.workingHours) };
  const yoeRaw = (resourceForm.yearsOfExperience ?? '').toString().trim();
  return {
    code: resourceForm.code.trim(),
    name: resourceForm.name.trim(),
    resource_type: resourceForm.resourceType,
    vertical_code: resourceForm.verticalCode,
    capabilities,
    bio: resourceForm.bio.trim() || null,
    photo_media_asset_id: resourceForm.photoMediaAssetId || null,
    specialty: resourceForm.specialty.trim() || null,
    license_number: resourceForm.licenseNumber.trim() || null,
    years_of_experience: yoeRaw ? Number.parseInt(yoeRaw, 10) : null,
    public_profile: Boolean(resourceForm.publicProfile),
  };
}
