/**
 * Configuración de navegación por shell de rol.
 *
 * Cada entrada es una sección con un título y una lista ordenada de `module id`
 * (definidos en `app/modules.js`). El label y la `capability` de cada item se
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
  { section: 'Inicio', items: ['dashboard', 'manager-analytics', 'onboarding-wizard'] },
  {
    section: 'Conversaciones',
    items: ['operations-desk', 'my-handoffs', 'contacts', 'campaigns', 'segments', 'digest-reports'],
  },
  { section: 'Hoy', items: ['appointments'] },
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
  // Módulo Ravit Studio (Influencer) — opt-in por tenant. `influencer-entry`
  // es un nav item especial: el `TenantShellRoute` lo filtra dinámicamente
  // según `tenant_modules.influencer.enabled` (consultado vía
  // `isInfluencerEnabled`) y al clickearlo navega a `/t/{slug}/influencer`
  // (en lugar de `/t/{slug}/influencer-entry`), abriendo el sub-shell con
  // su sub-nav propia (INFLUENCER_NAV).
  { section: 'Ravit Studio', items: ['influencer-entry'] },
  // Módulo Gestión Documental — opt-in por tenant (gobierno colombiano).
  // Mismo patrón que Ravit Studio: `gd-entry` es nav item especial filtrado
  // dinámicamente según `tenant_modules.gestion_documental.enabled`
  // (consultado vía `isGdEnabled`). Al clickearlo navega a `/t/{slug}/gd` y
  // abre el `GdShell` con su propia sub-nav rol-aware (definida en
  // `features/gd/shell/GdSidebar.jsx`, no acá — el módulo es autocontenido).
  { section: 'Gestión Documental', items: ['gd-entry'] },
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
  // Proveedores IA — config transversal de plataforma (no del módulo
  // Influencer). El shell filtra por capability `platform.ai_providers.configure`.
  {
    section: 'Proveedores IA',
    items: ['platform-ai-providers'],
  },
]);

// Viewer — shell read-only. Reusa los módulos de lectura del tenant; el shell
// los filtra a mode 'R' y oculta cualquier CTA de escritura. `viewer-summary`
// (UI-010.1) es la landing del Viewer, por eso encabeza la sección Lectura.
// `viewer-analytics` (UI-010.2) es la versión read-only del panel de analítica
// (wrapper fino sobre `AnalyticsPanel`). `viewer-appointments` (UI-010.3) es
// el listado paginado read-only de citas (reusa `AppointmentCard`).
// `viewer-conversations` (UI-010.4) es la lista read-only de conversaciones
// (reusa `InboxList` con `showStartForm={false}`, sin composer ni CTAs de
// handoff). Owner/Admin/Manager/Agent siguen usando `operations-desk` /
// `analytics` / `appointments` directamente vía `TENANT_NAV`.
export const VIEWER_NAV = Object.freeze([
  {
    section: 'Lectura',
    items: ['viewer-summary', 'viewer-analytics', 'viewer-appointments', 'viewer-conversations', 'contacts'],
  },
]);

// Módulo Influencer / Ravit Studio — UI-INFLU-002. Sub-nav del módulo, se
// muestra DENTRO del `InfluencerShell` (no se mezcla con `TENANT_NAV`). El
// shell filtra los items por `usePermissions().can('influencer.module.access', 'R')`
// y por capability específica de cada item, igual que el resto de nav.
//
// Mapping a HTMLs del diseñador (sidebar en docs/influencer/01..05):
//   - "Estudio · Generar contenido"  → casting (entry) + generate
//   - "Feed · Posts publicados"       → casting (con tab posts publicados)
//   - "Calendario · Programación"     → calendar
//   - "Stats · Rendimiento Global"    → casting con focus en stats
//   - "Casting · 6 personajes"        → casting
//   - "Biblioteca"                    → library (link a media-library existente)
//   - "Créditos · 248"                → credits
export const INFLUENCER_NAV = Object.freeze([
  { section: 'Estudio', items: ['influencer-casting'] },
  { section: 'Producción', items: ['influencer-calendar'] },
  { section: 'Recursos', items: ['influencer-library', 'influencer-credits'] },
]);
