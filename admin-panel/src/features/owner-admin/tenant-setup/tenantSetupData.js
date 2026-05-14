// TASK-0073: catálogo de países soportados con su locale/currency/timezone por
// defecto.  Cualquier país fuera de este set se rechaza en backend (schemas.py).
export const COUNTRY_PROFILES = {
  CO: { label: 'Colombia', locale: 'es-CO', currency: 'COP', timezone: 'America/Bogota' },
  MX: { label: 'México', locale: 'es-MX', currency: 'MXN', timezone: 'America/Mexico_City' },
  AR: { label: 'Argentina', locale: 'es-AR', currency: 'ARS', timezone: 'America/Argentina/Buenos_Aires' },
  CL: { label: 'Chile', locale: 'es-CL', currency: 'CLP', timezone: 'America/Santiago' },
  PE: { label: 'Perú', locale: 'es-PE', currency: 'PEN', timezone: 'America/Lima' },
  EC: { label: 'Ecuador', locale: 'es-EC', currency: 'USD', timezone: 'America/Guayaquil' },
  UY: { label: 'Uruguay', locale: 'es-UY', currency: 'UYU', timezone: 'America/Montevideo' },
};
export const SUPPORTED_COUNTRIES = ['CO', 'MX', 'AR', 'CL', 'PE', 'EC', 'UY'];

export const RETENTION_ENTITIES = [
  'messages',
  'conversations',
  'audit_logs',
  'domain_events',
  'webhook_events_raw',
  'reminder_jobs',
];
export const RETENTION_ANONYMIZABLE = new Set(['messages', 'conversations']);

export const wizardTabs = [
  { id: 'tenant', label: 'Negocio' },
  { id: 'calificacion', label: 'Calificación' },
  { id: 'settings', label: 'Settings' },
  { id: 'hours', label: 'Horarios' },
  { id: 'branches', label: 'Sedes' },
  { id: 'escalation', label: 'Escalamiento' },
  { id: 'intenciones', label: 'Intenciones' },
  { id: 'notificaciones', label: 'Notificaciones' },
  { id: 'pagos', label: 'Pagos' },
  { id: 'privacy', label: 'Privacidad' },
  { id: 'voz', label: 'Voz del bot' },
  { id: 'ia_rag', label: 'IA y RAG' },
  { id: 'audit', label: 'Auditoría' },
];

// TASK-0071: voz/personalidad del bot.
export const DEFAULT_BOT_PERSONALITY = {
  tone: 'neutral',
  formality: 'tu',
  emoji_level: 'moderate',
  custom_persona: '',
};

export const BOT_TONE_OPTIONS = [
  { value: 'neutral', label: 'Neutral', hint: 'Profesional, equilibrado, sin exageraciones.' },
  { value: 'formal', label: 'Formal', hint: 'Corporativo, pulido, sin coloquialismos.' },
  { value: 'friendly', label: 'Amigable', hint: 'Cálido, empático, conversacional.' },
  { value: 'playful', label: 'Divertido', hint: 'Desenfadado, con chispa moderada.' },
];

export const BOT_FORMALITY_OPTIONS = [
  { value: 'tu', label: 'Tú (informal)', hint: '"¿quieres agendar?"' },
  { value: 'usted', label: 'Usted (formal)', hint: '"¿desea agendar?"' },
  { value: 'vos', label: 'Vos (rioplatense)', hint: '"¿querés agendar?"' },
];

export const BOT_EMOJI_OPTIONS = [
  { value: 'none', label: 'Ninguno', hint: 'Sin emojis.' },
  { value: 'low', label: 'Bajo', hint: 'Máx 1 cada 3 mensajes.' },
  { value: 'moderate', label: 'Moderado', hint: '1-2 emojis por mensaje.' },
  { value: 'high', label: 'Alto', hint: '2-3 emojis por mensaje.' },
];

export const PERSONALITY_PREVIEW_SAMPLES = [
  {
    id: 'greeting',
    title: 'Saludo inicial',
    base: '¡Hola! Soy el asistente de {business_name}. ¿En qué te puedo ayudar?',
  },
  {
    id: 'availability',
    title: 'Consulta de disponibilidad',
    base: 'Tenemos disponibilidad el martes a las 10:00 o el jueves a las 16:00. ¿Cuál te conviene?',
  },
  {
    id: 'objection',
    title: 'Manejo de objeción de precio',
    base: 'Entiendo que el precio es importante. Tenemos una versión más económica que también funciona excelente.',
  },
];

export const DEFAULT_NOTIFICATION_SETTINGS = {
  confirmation_enabled: true,
  reminder_24h_enabled: true,
  reminder_1h_enabled: false,
  include_location_link: true,
  location_address: '',
  location_maps_url: '',
  include_preparation_notes: true,
  no_show_confirmation_enabled: true,
  confirmation_reminder_hours: 4,
  post_instructions_enabled: true,
  post_instructions_delay_minutes: 30,
  post_feedback_enabled: true,
  post_feedback_delay_hours: 2,
  post_rebooking_enabled: false,
  post_rebooking_delay_days: 30,
  post_rebooking_message: '',
  auto_rebook_on_decline: true,
  auto_rebook_timeout_minutes: 90,
  vip_budget_threshold: 0,
  ask_referrer: false,
  complaint_alert_channels: {
    email: [],
    whatsapp: [],
    webhook_url: '',
  },
};

export const ALL_INTENTS_META = [
  { id: 'greeting', label: 'Saludo', description: 'Apertura o reapertura de conversación.' },
  { id: 'faq', label: 'FAQ', description: 'Pregunta informativa (precios, horarios, servicios).' },
  { id: 'book_appointment', label: 'Agendar cita', description: 'Quiere agendar una cita nueva.' },
  { id: 'confirm_appointment', label: 'Confirmar cita', description: 'Consulta o confirma una cita existente.' },
  { id: 'reschedule_appointment', label: 'Reagendar cita', description: 'Quiere mover una cita a otro horario.' },
  { id: 'cancel_appointment', label: 'Cancelar cita', description: 'Quiere cancelar una cita.' },
  { id: 'check_availability', label: 'Consultar disponibilidad', description: 'Pregunta por disponibilidad sin comprometerse.' },
  { id: 'complaint_or_risk', label: 'Queja / Riesgo', description: 'Queja, reclamación o frustración — fuerza handoff.' },
  { id: 'out_of_scope', label: 'Fuera de scope', description: 'Mensaje sin relación con el negocio.' },
  { id: 'opt_out', label: 'Opt-out', description: 'El usuario pide no recibir más mensajes.' },
];

export const DEFAULT_INTENT_KEYWORDS = {
  greeting: ['hola', 'buenos días', 'buenas tardes', 'buenas noches', 'hey', 'saludos', 'buen día'],
  faq: ['información', 'cuánto cuesta', 'precio', 'horario', 'cómo funciona', 'qué ofrecen', 'dónde están'],
  book_appointment: ['quiero una cita', 'agendar', 'reservar', 'turno', 'appointment', 'necesito cita', 'pedir hora'],
  confirm_appointment: ['confirmar', 'confirmación', 'tengo cita', 'mi cita', 'está agendado', 'queda confirmada'],
  reschedule_appointment: ['reagendar', 'cambiar cita', 'mover cita', 'otro horario', 'reprogramar', 'otra fecha'],
  cancel_appointment: ['cancelar', 'cancela mi cita', 'no puedo ir', 'ya no quiero', 'quiero cancelar'],
  check_availability: ['disponibilidad', 'tienen lugar', 'hay espacio', 'qué días tienen', 'qué horarios tienen'],
  complaint_or_risk: ['queja', 'reclamo', 'estafa', 'fraude', 'mal servicio', 'indignado', 'insatisfecho', 'terrible', 'pésimo'],
  out_of_scope: [],
  opt_out: ['stop', 'baja', 'no me escribas', 'no quiero mensajes', 'cancelar suscripción', 'darme de baja'],
};

export const embeddingProviderOptions = [
  {
    value: 'local_hash',
    label: 'Local hash (sin API)',
    description: 'SHA-256 determinístico. No requiere API key. Útil solo para desarrollo; la búsqueda semántica no funciona.',
    defaultModel: 'copilotoia-local-hash-v1',
    defaultDims: 1536,
  },
  {
    value: 'openai',
    label: 'OpenAI',
    description: 'text-embedding-3-small (1536 dims) o text-embedding-3-large (3072 dims). Requiere API key de OpenAI.',
    defaultModel: 'text-embedding-3-small',
    defaultDims: 1536,
  },
  {
    value: 'anthropic',
    label: 'Anthropic / Voyage',
    description: 'voyage-3-lite (1024 dims) via Voyage AI. Requiere API key de Voyage (api.voyageai.com).',
    defaultModel: 'voyage-3-lite',
    defaultDims: 1024,
  },
  {
    value: 'ollama',
    label: 'Ollama (local)',
    description: 'Modelo de embeddings local via Ollama. Sin costo de API; requiere Ollama corriendo en el servidor.',
    defaultModel: 'nomic-embed-text',
    defaultDims: 768,
  },
];

export const weekdays = [
  ['mon', 'Lunes'],
  ['tue', 'Martes'],
  ['wed', 'Miércoles'],
  ['thu', 'Jueves'],
  ['fri', 'Viernes'],
  ['sat', 'Sábado'],
  ['sun', 'Domingo'],
];

export const initialHours = weekdays.reduce((hours, [day], index) => {
  hours[day] = { enabled: index < 5, start: '09:00', end: '18:00' };
  return hours;
}, {});

export const defaultPiiRules = {
  phone: 'mask',
  email: 'mask',
  address: 'redact',
  government_id: 'redact',
};

export const availableStatusTransitions = {
  trial: [{ value: 'active', label: 'Activar (trial → active)' }, { value: 'suspended', label: 'Suspender (trial → suspended)' }, { value: 'churned', label: 'Dar de baja (trial → churned)' }],
  active: [{ value: 'suspended', label: 'Suspender (active → suspended)' }, { value: 'churned', label: 'Dar de baja (active → churned)' }],
  suspended: [{ value: 'active', label: 'Reactivar (suspended → active)' }, { value: 'churned', label: 'Dar de baja (suspended → churned)' }],
  churned: [],
};
