/**
 * UI-016.7 — datos y catálogos estáticos para Cuenta del usuario.
 *
 * Toda la pantalla `T3 _ Cuenta del usuario.html` es transversal y previa al
 * backend (`UI-016.7-FU` lo declara). Mientras los endpoints `/me/profile`,
 * `/me/preferences`, `/me/notifications` y `/me/sessions` no existen, estos
 * helpers proveen:
 *   - el catálogo de idiomas y zonas horarias del select,
 *   - la matriz canónica de eventos × canales (estado inicial: el del HTML),
 *   - la lista demo de sesiones activas (read-only mientras no haya backend),
 *   - utilidades para derivar nombre / iniciales del `profile` de Auth0
 *     (`useAuth().session.profile`).
 *
 * Mantener este módulo libre de React: solo datos y funciones puras, así los
 * tests cubren la lógica con `vitest` sin renderizar nada.
 */

export const ACCOUNT_LOCALES = [
  { value: 'es-CO', label: 'Español (Colombia) — es-CO' },
  { value: 'es-MX', label: 'Español (México) — es-MX' },
  { value: 'es-ES', label: 'Español (España) — es-ES' },
  { value: 'en-US', label: 'English (United States) — en-US' },
  { value: 'pt-BR', label: 'Português (Brasil) — pt-BR' },
];

export const ACCOUNT_TIMEZONES = [
  { value: 'America/Bogota', label: 'America/Bogotá (UTC−5)' },
  { value: 'America/Mexico_City', label: 'America/Ciudad de México (UTC−6)' },
  { value: 'America/Lima', label: 'America/Lima (UTC−5)' },
  { value: 'America/Santiago', label: 'America/Santiago (UTC−4)' },
  { value: 'America/Buenos_Aires', label: 'America/Buenos Aires (UTC−3)' },
  { value: 'America/Sao_Paulo', label: 'America/São Paulo (UTC−3)' },
  { value: 'Europe/Madrid', label: 'Europe/Madrid (UTC+1)' },
];

export const NOTIFICATION_CHANNELS = [
  { id: 'email', label: 'Email' },
  { id: 'wa', label: 'WhatsApp' },
  { id: 'inapp', label: 'En la app' },
];

/**
 * Catálogo canónico de eventos × canales. El `default` es el estado preseleccionado
 * que pintan los checkboxes del HTML (`true` = canal activo para ese evento).
 */
export const NOTIFICATION_EVENTS = [
  {
    id: 'daily_digest',
    title: 'Digest diario',
    description: '08:00 hora local · resumen del negocio',
    defaults: { email: true, wa: true, inapp: false },
  },
  {
    id: 'handoff_sla',
    title: 'Handoff con SLA cercano',
    description: 'cuando una conversación tuya queda < 10 min de SLA',
    defaults: { email: true, wa: false, inapp: true },
  },
  {
    id: 'payment_failed',
    title: 'Cobro fallido',
    description: 'cualquier suscripción del tenant',
    defaults: { email: true, wa: false, inapp: false },
  },
  {
    id: 'appointment_confirmed',
    title: 'Cita confirmada',
    description: 'cliente confirma su cita por bot',
    defaults: { email: false, wa: false, inapp: true },
  },
  {
    id: 'quality_rating_low',
    title: 'Quality rating de WhatsApp baja',
    description: 'cuando Meta reduce el rating del canal',
    defaults: { email: true, wa: false, inapp: true },
  },
  {
    id: 'weekly_campaigns_summary',
    title: 'Resumen semanal de campañas',
    description: 'lunes 09:00',
    defaults: { email: true, wa: false, inapp: false },
  },
];

export const THEME_OPTIONS = [
  { value: 'auto', label: 'Auto', description: 'Sigue al SO' },
  { value: 'light', label: 'Claro', description: 'Off-white' },
  { value: 'dark', label: 'Oscuro', description: 'Ink + bone' },
];

/**
 * Estado demo de "sesiones activas" — read-only hasta que exista `/me/sessions`.
 * El HTML T3 menciona "Última sesión: 14 may · 09:42 · Bogotá · Chrome 124 / macOS".
 * Marcamos `current: true` en la fila actual y dejamos otra como ejemplo.
 */
export const DEFAULT_SESSIONS = [
  {
    id: 'session-current',
    device: 'Chrome 124 · macOS',
    location: 'Bogotá, Colombia',
    last_seen_label: 'ahora · sesión activa',
    current: true,
  },
  {
    id: 'session-mobile',
    device: 'WhatsApp Web · iPhone 15 · iOS 17',
    location: 'Bogotá, Colombia',
    last_seen_label: 'hace 2 días',
    current: false,
  },
  {
    id: 'session-old',
    device: 'Firefox 125 · Ubuntu',
    location: 'Medellín, Colombia',
    last_seen_label: 'hace 11 días',
    current: false,
  },
];

/**
 * Genera el shape inicial del formulario de Perfil a partir del profile del
 * session de Auth0. El email es siempre read-only (lo controla Auth0). Si
 * `profile?.name` no viene, intentamos un fallback razonable.
 */
export function deriveProfileForm(profile) {
  const name = profile?.name || profile?.email?.split('@')[0] || '';
  const email = profile?.email || '';
  const phone = profile?.phone_number || profile?.phone || '';
  return {
    name,
    email,
    phone,
    locale: 'es-CO',
    timezone: 'America/Bogota',
  };
}

/**
 * Inicializa la matriz de notificaciones (event_id → { email, wa, inapp }) con
 * los defaults del catálogo. Esta función no toca localStorage: las
 * preferencias persistirán cuando UI-016.7-FU entregue `/me/notifications`.
 */
export function initialNotificationMatrix() {
  return NOTIFICATION_EVENTS.reduce((acc, event) => {
    acc[event.id] = { ...event.defaults };
    return acc;
  }, {});
}

/**
 * Toggle de un canal en la matriz de notificaciones; devuelve una matriz nueva
 * (inmutable) para que React detecte el cambio.
 */
export function toggleNotificationChannel(matrix, eventId, channelId) {
  const current = matrix[eventId] || {};
  return {
    ...matrix,
    [eventId]: { ...current, [channelId]: !current[channelId] },
  };
}

/**
 * Iniciales para el avatar a partir del profile. Mismo algoritmo que
 * `ShellSidebar.userInitials` pero exportado para reuso en el AccountShell.
 */
export function profileInitials(profile) {
  const source = profile?.name || profile?.email || profile?.sub || 'U';
  const parts = source.trim().split(/\s+/);
  const initials = parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
  return initials.toUpperCase();
}

export function profileDisplayName(profile) {
  return profile?.name || profile?.email || profile?.sub || 'Usuario';
}

export function profileRoleLabel(profile) {
  if (!profile?.roles?.length) return 'sin rol';
  // Si el usuario tiene varios roles, el sidebar muestra el primero — el panel
  // de cuenta usa la misma convención para no contradecirlo.
  return profile.roles[0];
}
