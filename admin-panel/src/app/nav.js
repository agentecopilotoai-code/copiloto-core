/**
 * Branch `core` — navegación del sistema operativo.
 *
 * Solo platform admin + transversales del tenant. Cuando se "instala" un
 * módulo sobre el core, agrega su propia sección a `TENANT_NAV` (vía hook
 * de carga dinámica — TODO Fase 2).
 *
 * Cada entrada es una sección con un título y una lista ordenada de
 * `module id` (definidos en `app/modules.js`). El label y la `capability`
 * de cada item se resuelven contra `adminModules`.
 *
 * El shell filtra los items por `usePermissions().can(capability, 'R')` y
 * omite los `id` no registrados.
 */

// Owner / Admin / Manager / Agent — shell tenant-scoped.
//
// Sin módulos de producto instalados, el sidebar tenant solo expone
// la sección "Configuración" (tenant-setup, team). Un tenant fresco
// sin módulos es un tenant útil solo para configurarse.
export const TENANT_NAV = Object.freeze([
  { section: 'Configuración', items: ['tenant-setup', 'team'] },
]);

// Platform Owner — shell de flota, sin selector de tenant. Sistema operativo
// del core completo.
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
  { section: 'Runbooks', items: ['platform-runbooks'] },
  {
    section: 'Acceso',
    items: ['platform-roles-acl', 'platform-feature-flags'],
  },
  {
    // Recurso transversal — config IA cross-modalidad consumida por
    // cualquier módulo de producto que se instale sobre el core.
    section: 'Proveedores IA',
    items: ['platform-ai-providers'],
  },
  {
    // v2.0.0 — multi-provider email (Resend, SendGrid, Mailgun, SMTP).
    // Recurso transversal: cualquier módulo que necesite enviar email
    // pasa por el `EmailDispatcher` que recorre los providers activos.
    section: 'Proveedores de email',
    items: ['platform-email-providers'],
  },
]);

// Viewer — shell read-only. En el core base no hay módulos del producto
// con vista de viewer; queda vacío hasta que un módulo se instale.
export const VIEWER_NAV = Object.freeze([]);
