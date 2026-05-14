/**
 * Configuración de navegación por shell de rol.
 *
 * Cada entrada es una sección con un título y una lista ordenada de `module id`
 * (definidos en `data/modules.js`). El label y la `capability` de cada item se
 * resuelven contra `adminModules` — esto evita duplicar metadata.
 *
 * El shell filtra los items por `usePermissions().can(capability, 'R')` y omite
 * los `id` que todavía no estén registrados como módulo (las vistas de Platform
 * Owner se registran en UI-006). Las secciones que queden sin items visibles no
 * se renderizan.
 *
 * Fuente visual de las agrupaciones: sidebars de `docs/HTML DESIGN/` por rol.
 */

// Owner / Admin / Manager / Agent — shell tenant-scoped.
export const TENANT_NAV = Object.freeze([
  { section: 'Inicio', items: ['onboarding-wizard'] },
  {
    section: 'Conversaciones',
    items: ['operations-desk', 'contacts', 'campaigns', 'segments'],
  },
  {
    section: 'Negocio',
    items: ['services', 'packages', 'subscriptions', 'branches', 'analytics'],
  },
  {
    section: 'IA & Canales',
    items: [
      'whatsapp',
      'social-channels',
      'knowledge-studio',
      'knowledge-storage',
      'media-library',
    ],
  },
  { section: 'Operación', items: ['outbound-dlq', 'go-live-readiness'] },
  { section: 'Configuración', items: ['tenant-setup', 'team', 'legal', 'audit'] },
]);

// Platform Owner — shell de flota, sin selector de tenant. Las vistas
// `platform-*` distintas de `platform-fleet` se registran en UI-006.
export const PLATFORM_NAV = Object.freeze([
  {
    section: 'Plataforma',
    items: ['platform-fleet', 'platform-system-health'],
  },
  { section: 'Observability', items: ['platform-billing'] },
  {
    section: 'Operaciones',
    items: ['platform-incidents', 'platform-fleet-dlq'],
  },
  { section: 'Audit global', items: ['platform-runbooks'] },
  {
    section: 'Acceso',
    items: ['platform-roles-acl', 'platform-feature-flags'],
  },
]);

// Viewer — shell read-only. Reusa los módulos de lectura del tenant; el shell
// los filtra a mode 'R' y oculta cualquier CTA de escritura.
export const VIEWER_NAV = Object.freeze([
  {
    section: 'Lectura',
    items: ['analytics', 'appointments', 'operations-desk', 'contacts'],
  },
]);
