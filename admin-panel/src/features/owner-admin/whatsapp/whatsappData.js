/**
 * UI-007.8 — Canales · WhatsApp Cloud API: pure data helpers.
 *
 * Template/channel constants, form shapes, the Meta-components builder and the
 * onboarding-checklist derivation — extracted verbatim from the legacy
 * `WhatsAppOnboarding` so the wizard / health / templates panels share them and
 * they stay unit-testable without React.
 */

/** Channel tabs (WhatsApp Cloud API + the web widget). */
export const CHANNEL_TABS = [
  { id: 'whatsapp', label: 'WhatsApp Cloud API' },
  { id: 'web', label: 'Widget Web' },
];

/** Message-template purposes, mirrored from the backend enum. */
export const TEMPLATE_PURPOSES = [
  { id: 'appointment_confirmation', label: 'Confirmación de cita', required: true },
  { id: 'appointment_reminder_24h', label: 'Recordatorio 24 h', required: true },
  { id: 'appointment_reminder_1h', label: 'Recordatorio 1 h' },
  { id: 'appointment_reminder_custom', label: 'Recordatorio personalizado' },
  { id: 'no_show_confirmation_request', label: 'Pedido de confirmación (no-show)' },
  { id: 'no_show_followup', label: 'Seguimiento no-show' },
  { id: 'post_appointment_instructions', label: 'Instrucciones post-cita' },
  { id: 'post_appointment_feedback', label: 'Feedback post-cita' },
  { id: 'post_appointment_rebooking', label: 'Invitación a nueva cita' },
  { id: 'reschedule_offer', label: 'Oferta de reagendamiento' },
  { id: 'campaign_promo', label: 'Campaña / promoción' },
  { id: 'payment_request', label: 'Solicitud de pago' },
  { id: 'custom', label: 'Personalizado' },
];

/** Spanish labels for a template's Meta review status. */
export const TEMPLATE_STATUS_LABEL = {
  draft: 'Borrador',
  pending: 'Pendiente',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  paused: 'Pausado',
};

/** `StatusBadge` tone for a template's Meta review status. */
export const TEMPLATE_STATUS_TONE = {
  draft: 'neutral',
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  paused: 'neutral',
};

/** The five onboarding steps shown in the wizard checklist. */
export const ONBOARDING_STEPS = [
  {
    id: 'business',
    label: 'Business Manager conectado',
    description: 'Registra el Business ID de Meta que administra el portafolio de WhatsApp.',
  },
  {
    id: 'waba',
    label: 'WABA identificado',
    description: 'Asocia el WhatsApp Business Account ID del tenant.',
  },
  {
    id: 'phone',
    label: 'Phone Number ID listo',
    description: 'Configura el número que recibirá webhooks y enviará mensajes.',
  },
  {
    id: 'secrets',
    label: 'Secretos del tenant guardados',
    description: 'Pega los tres secretos del canal; CopilotoIA los guarda en la estructura fija del tenant.',
  },
  {
    id: 'health',
    label: 'Health check validado',
    description: 'Confirma que el canal está activo en CopilotoIA y listo para pruebas controladas.',
  },
];

/** A blank message-template form. */
export function emptyTemplateForm() {
  return {
    name: '',
    locale: 'es',
    category: 'utility',
    purpose: 'appointment_confirmation',
    header: '',
    body: '',
    footer: '',
    buttons: '',
  };
}

/** The default channel form for a tenant with no WhatsApp channel yet. */
export function defaultFormForTenant() {
  return {
    business_id: '',
    waba_id: '',
    phone_number_id: '',
    account_mode: 'mock',
    meta_access_token: '',
    app_secret: '',
    verify_token: '',
  };
}

/** Build the channel form from a loaded channel record (secrets stay blank). */
export function formFromChannel(channel) {
  return {
    business_id: channel.business_id || '',
    waba_id: channel.waba_id || '',
    phone_number_id: channel.phone_number_id || '',
    account_mode: channel.account_mode || defaultFormForTenant().account_mode,
    meta_access_token: '',
    app_secret: '',
    verify_token: '',
  };
}

/** Translate the flat template form into the Meta `components` object. */
export function templateComponentsFromForm(form) {
  const components = {};
  if (form.header.trim()) {
    components.header = { type: 'text', text: form.header.trim() };
  }
  if (form.body.trim()) {
    components.body = { text: form.body.trim() };
  }
  if (form.footer.trim()) {
    components.footer = { text: form.footer.trim() };
  }
  const buttons = form.buttons
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text) => ({ type: 'QUICK_REPLY', text }));
  if (buttons.length) {
    components.buttons = buttons;
  }
  return components;
}

/** True when `value` has non-whitespace content. */
export function hasValue(value) {
  return Boolean(String(value || '').trim());
}

/** Pull the channel record out of a health response. */
export function channelFromHealth(health) {
  return health?.channel || null;
}

/**
 * Validate the new-template form. Returns an error string when the name/body
 * are missing or the name is not snake_case, otherwise `null`.
 */
export function validateTemplateForm(form) {
  if (!form.name.trim() || !form.body.trim()) {
    return 'Nombre y body son obligatorios.';
  }
  if (!/^[a-z0-9_]+$/.test(form.name.trim())) {
    return 'El nombre debe ser snake_case (a-z, 0-9, _).';
  }
  return null;
}

/** Group templates by their `purpose`. */
export function groupTemplatesByPurpose(templates) {
  const map = {};
  templates.forEach((template) => {
    const list = map[template.purpose] || [];
    list.push(template);
    map[template.purpose] = list;
  });
  return map;
}

/**
 * Derive the onboarding checklist (each `ONBOARDING_STEPS` entry + `done`).
 * Logic preserved verbatim from the legacy module.
 */
export function buildChecklist(form, health, channel) {
  const hasSecrets =
    (health?.checks?.meta_access_token_configured &&
      health?.checks?.app_secret_configured &&
      health?.checks?.verify_token_configured) ||
    (hasValue(form.meta_access_token) &&
      hasValue(form.app_secret) &&
      hasValue(form.verify_token));
  const healthOk = channel?.status === 'active' && health?.status === 'healthy';

  return ONBOARDING_STEPS.map((step) => {
    const done = {
      business: hasValue(form.business_id),
      waba: hasValue(form.waba_id),
      phone: hasValue(form.phone_number_id),
      secrets: hasSecrets,
      health: healthOk,
    }[step.id];
    return { ...step, done };
  });
}

/**
 * Required-template semaphore: for each required purpose, 'green' when an
 * approved template exists, 'yellow' when one is pending, 'red' otherwise.
 */
export function buildRequiredSemaphore(templatesByPurpose) {
  return TEMPLATE_PURPOSES.filter((p) => p.required).map((purpose) => {
    const items = templatesByPurpose[purpose.id] || [];
    const approved = items.find((t) => t.status === 'approved');
    const pending = items.find((t) => t.status === 'pending');
    if (approved) return { id: purpose.id, label: purpose.label, tone: 'green', text: 'Aprobada' };
    if (pending) return { id: purpose.id, label: purpose.label, tone: 'yellow', text: 'Pendiente' };
    return { id: purpose.id, label: purpose.label, tone: 'red', text: 'Faltante' };
  });
}
