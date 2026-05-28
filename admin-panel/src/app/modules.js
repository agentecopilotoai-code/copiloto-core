/**
 * Branch `core` — adminModules del sistema operativo.
 *
 * Solo platform admin (cross-tenant) + transversales del tenant. NINGÚN
 * módulo de producto opt-in está hardcodeado acá.
 *
 * Cuando se "instala" un módulo sobre el core, ese módulo agrega su
 * propia entrada a esta lista (vía un hook de carga dinámica, TODO Fase 2).
 */
export const adminModules = [
  // ─── Platform admin (cross-tenant) ────────────────────────────────────────
  {
    id: 'platform-fleet',
    label: 'Fleet · Tenants',
    summary: 'Vista cross-tenant: listado, filtros, detalle y "Operar como tenant" (support_mode).',
    scope: ['Listado de tenants', 'Filtros por status/país/vertical', 'KPIs agregados', 'Drawer de detalle', 'Entrada a support_mode auditado'],
    capability: 'platform.tenants.read',
  },
  {
    id: 'platform-system-health',
    label: 'System Health',
    summary: 'Estado en vivo de la plataforma: latencia, procesos de fondo, proveedores y alertas activas.',
    scope: ['KPIs de salud', 'Latencia p50/p95/p99', 'Estado por servicio', 'Circuit breakers'],
    capability: 'platform.system_health.read',
  },
  {
    id: 'platform-billing',
    label: 'Billing & MRR',
    summary: 'Ingreso recurrente mensual agregado por moneda, plan, negocio y país.',
    scope: ['MRR consolidado por moneda', 'Composición del MRR por plan', 'Tenants por plan', 'Churn 30d'],
    capability: 'platform.billing.read',
  },
  {
    id: 'platform-incidents',
    label: 'Incidentes',
    summary: 'Alertas operativas de toda la plataforma con severidad y guía de resolución.',
    scope: ['Lista de incidentes con severidad', 'Filtros por estado y tipo', 'Drawer con payload y timeline'],
    capability: 'platform.incidents.read',
  },
  {
    id: 'platform-fleet-dlq',
    label: 'Outbound DLQ',
    summary: 'Mensajes salientes no entregados, agregados por negocio y motivo del error.',
    scope: ['Fallos agregados por tenant', 'Distribución por error code', 'Reintento masivo con confirmación'],
    capability: 'platform.outbound_dlq.read',
  },
  {
    id: 'platform-runbooks',
    label: 'Runbooks',
    summary: 'Catálogo de guías operacionales con búsqueda, filtro por categoría y visor seguro.',
    scope: ['Catálogo de guías', 'Búsqueda', 'Filtro por categoría', 'Visor seguro'],
    capability: 'platform.runbooks.read',
  },
  {
    id: 'platform-roles-acl',
    label: 'Roles & ACL',
    summary: 'Matriz de permisos del sistema operativo: capacidades del chrome del panel × rol. CRUD pendiente Fase 2.',
    scope: ['Matriz capacidad × rol', 'Política de roles'],
    capability: 'platform.roles_acl.read',
  },
  {
    id: 'platform-feature-flags',
    label: 'Feature flags',
    summary: 'Catálogo de feature flags del sistema. CRUD pendiente Fase 2.',
    scope: ['Catálogo de feature flags', 'Búsqueda', 'Estado default y rollout %'],
    capability: 'platform.feature_flags.read',
  },
  {
    // Proveedores IA transversales — alimentan cualquier módulo de producto
    // opt-in que se instale sobre el core.
    id: 'platform-ai-providers',
    label: 'Proveedores IA',
    summary: 'Configuración cross-modalidad (llm/image/video/tts/stt) de los proveedores IA. Recurso transversal — cualquier módulo del producto lo consume.',
    scope: ['Catálogo de modalidades', 'Provider + modelo por modalidad', 'Rotación de secret (write-only)', 'Hint público (últimos 4 chars)'],
    capability: 'platform.ai_providers.configure',
  },
  {
    // v2.0.0 — multi-provider email (Resend, SendGrid, Mailgun, SMTP) con
    // fallback chain por prioridad. Reusa la misma capability que AI providers
    // (`platform.ai_providers.configure`) para no agregar otra cap nueva al
    // RBAC; el platform_owner ya tiene ambas naturalmente.
    id: 'platform-email-providers',
    label: 'Proveedores de email',
    summary: 'Configuración multi-provider (Resend, SendGrid, Mailgun, SMTP) con fallback chain por prioridad. Reemplaza el wrapper Resend hardcodeado.',
    scope: ['CRUD de providers', 'Rotación de API key (write-only)', 'Test endpoint por provider', 'Audit en app.email_dispatch_log'],
    capability: 'platform.ai_providers.configure',
  },

  // ─── Tenant transversales ────────────────────────────────────────────────
  {
    id: 'tenant-setup',
    label: 'Configuración del tenant',
    summary: 'Wizard de configuración base del tenant (datos institucionales, módulos activos, branding).',
    scope: ['Datos institucionales', 'Activación de módulos', 'Branding/logo'],
    capability: null,
  },
  {
    id: 'team',
    label: 'Equipo',
    summary: 'Gestión de usuarios del tenant y sus roles del chrome (owner/admin/manager/agent/viewer).',
    scope: ['Listado de miembros', 'Invitar usuarios', 'Asignar/revocar roles'],
    capability: 'team.write',
  },
];
