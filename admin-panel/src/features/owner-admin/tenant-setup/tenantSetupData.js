/**
 * Tenant setup wizard — datos compartidos entre tabs.
 *
 * Solo lo transversal del core. Los productos que se instalen sobre el
 * core agregan sus propios tabs vía un mecanismo de extensión (TODO).
 */

// Países soportados — cualquier país fuera de este set se rechaza en el
// schema backend (`app.services.locale.SUPPORTED_COUNTRIES`).
export const COUNTRY_PROFILES = {
  CO: { label: 'Colombia',  locale: 'es-CO', currency: 'COP', timezone: 'America/Bogota' },
  MX: { label: 'México',    locale: 'es-MX', currency: 'MXN', timezone: 'America/Mexico_City' },
  AR: { label: 'Argentina', locale: 'es-AR', currency: 'ARS', timezone: 'America/Argentina/Buenos_Aires' },
  CL: { label: 'Chile',     locale: 'es-CL', currency: 'CLP', timezone: 'America/Santiago' },
  PE: { label: 'Perú',      locale: 'es-PE', currency: 'PEN', timezone: 'America/Lima' },
  EC: { label: 'Ecuador',   locale: 'es-EC', currency: 'USD', timezone: 'America/Guayaquil' },
  UY: { label: 'Uruguay',   locale: 'es-UY', currency: 'UYU', timezone: 'America/Montevideo' },
};
export const SUPPORTED_COUNTRIES = Object.keys(COUNTRY_PROFILES);

// Tabs del wizard. Solo los transversales del core.
export const wizardTabs = [
  { id: 'tenant', label: 'Negocio' },
];

// Transiciones permitidas del lifecycle del tenant.
export const availableStatusTransitions = {
  trial:     [{ value: 'active', label: 'Activar' }, { value: 'suspended', label: 'Suspender' }, { value: 'churned', label: 'Dar de baja' }],
  active:    [{ value: 'suspended', label: 'Suspender' }, { value: 'churned', label: 'Dar de baja' }],
  suspended: [{ value: 'active', label: 'Reactivar' }, { value: 'churned', label: 'Dar de baja' }],
  churned:   [],
};
