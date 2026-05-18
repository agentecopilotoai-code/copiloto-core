/**
 * UI-007.2 — Onboarding self-service: step catalogue + pure status helper.
 *
 * The 7-step catalogue and the per-step status derivation are kept here so the
 * status logic is unit-testable without React. The verification / completion
 * logic itself stays in the view — the server is the authority for each step
 * (TASK-0069: the wizard rejects skipping with 409).
 */

// TASK-0069: 7-step self-service wizard with server-side verification.
export const ONBOARDING_STEPS = [
  {
    step: 1,
    key: 'business_details',
    label: 'Datos del negocio',
    helper: 'Slug, razón social, vertical, país y zona horaria del tenant. Edítalo en Tenant Setup → Negocio.',
    goToModule: 'tenant-setup',
  },
  {
    step: 2,
    key: 'locale_currency',
    label: 'Timezone, locale y moneda',
    helper: 'Locale y moneda derivan del país. Configúralo en Tenant Setup → Settings y Pagos.',
    goToModule: 'tenant-setup',
  },
  {
    step: 3,
    key: 'whatsapp_channel',
    label: 'Canal WhatsApp (firma verificada contra Meta)',
    helper: 'Pega Business ID, WABA ID, Phone Number ID, access token, app secret y verify token. La firma del webhook se valida contra Meta.',
    goToModule: 'whatsapp',
  },
  {
    step: 4,
    key: 'consent_template',
    label: 'Plantilla de opt-in aprobada',
    helper: 'Crea y sincroniza con Meta la plantilla de consentimiento. Solo avanza cuando Meta la aprueba.',
    goToModule: 'whatsapp',
  },
  {
    step: 5,
    key: 'service_catalog',
    label: 'Catálogo mínimo (≥ 1 servicio)',
    helper: 'El bot no puede agendar sin saber qué se ofrece. Crea al menos un servicio activo.',
    goToModule: 'services',
  },
  {
    step: 6,
    key: 'business_hours',
    label: 'Horarios de atención',
    helper: 'Define los rangos de atención en Tenant Setup → Horarios. Al menos un día con rangos.',
    goToModule: 'tenant-setup',
  },
  {
    step: 7,
    key: 'end_to_end_test',
    label: 'Test E2E del bot',
    helper: 'Envía un mensaje de prueba al wa_id del admin y verifica que llegue un inbound de respuesta.',
    goToModule: null,
  },
];

export const ONBOARDING_TOTAL_STEPS = ONBOARDING_STEPS.length;

/**
 * Derive a step's status from the last completed step number.
 *
 * @param {number} stepNumber 1-based step number
 * @param {number} lastCompleted last step the server marked complete (0 = none)
 * @returns {'done'|'current'|'blocked'}
 */
export function stepStatus(stepNumber, lastCompleted) {
  const completed = Number(lastCompleted) || 0;
  if (stepNumber <= completed) return 'done';
  if (stepNumber === completed + 1) return 'current';
  return 'blocked';
}
