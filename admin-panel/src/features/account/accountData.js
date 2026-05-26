/**
 * Datos y catálogos estáticos para Cuenta del usuario.
 *
 * Solo lo transversal del core: idiomas, zonas horarias, canales de
 * notificación, eventos de notificación core y sesiones activas demo.
 * Los módulos opt-in extienden estos catálogos con sus propios eventos.
 *
 * Mantener libre de React: solo datos y funciones puras.
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

// Canales de notificación core: solo email + in-app. Los módulos opt-in
// agregan sus propios canales (ej. un módulo de mensajería agrega su canal).
export const NOTIFICATION_CHANNELS = [
  { id: 'email', label: 'Email' },
  { id: 'inapp', label: 'En la app' },
];

// Catálogo de eventos del core. Cada módulo opt-in suma sus propios eventos.
export const NOTIFICATION_EVENTS = [
  {
    id: 'security_alert',
    title: 'Alerta de seguridad',
    description: 'login sospechoso, cambio de password, nueva sesión',
    defaults: { email: true, inapp: true },
  },
  {
    id: 'tenant_invite',
    title: 'Invitación a un negocio',
    description: 'cuando te invitan como miembro de un tenant',
    defaults: { email: true, inapp: true },
  },
  {
    id: 'role_changed',
    title: 'Cambio de rol',
    description: 'cuando tu rol en un negocio cambia',
    defaults: { email: true, inapp: true },
  },
  {
    id: 'support_mode_used',
    title: 'Soporte ingresó a tu negocio',
    description: 'platform owner activó support_mode en tu tenant',
    defaults: { email: true, inapp: false },
  },
];

export const THEME_OPTIONS = [
  { value: 'auto', label: 'Auto', description: 'Sigue al SO' },
  { value: 'light', label: 'Claro', description: 'Off-white' },
  { value: 'dark', label: 'Oscuro', description: 'Ink + bone' },
];

// Sesiones demo — usadas como fallback hasta que `/me/sessions` entregue
// el listado real desde el backend.
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
    device: 'Safari · iPhone 15 · iOS 17',
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
 * Shape inicial del form de perfil a partir del profile de Auth0.
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
 * Matriz inicial de notificaciones (event_id → { email, inapp }) con defaults.
 */
export function initialNotificationMatrix() {
  return NOTIFICATION_EVENTS.reduce((acc, event) => {
    acc[event.id] = { ...event.defaults };
    return acc;
  }, {});
}

/**
 * Toggle inmutable de un canal de notificación.
 */
export function toggleNotificationChannel(matrix, eventId, channelId) {
  const current = matrix[eventId] || {};
  return {
    ...matrix,
    [eventId]: { ...current, [channelId]: !current[channelId] },
  };
}

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
  return profile.roles[0];
}
