/**
 * urls.js — Source of truth de TODAS las URLs del admin-panel.
 *
 * Esquema canónico (decisión D-ROUTES-01, 2026-05-25):
 *
 *   /admin/*                              → platform admin (sin tenant)
 *   /{module}/t/{slug}/...                → operación dentro del tenant
 *   /{module}/admin/t/{slug}/...          → admin del módulo en el tenant
 *
 * Módulos actuales: `gd`, `influencer`, `chatbot`.
 *
 * Reglas:
 *  - El primer segmento es SIEMPRE el módulo (o `admin` para platform).
 *  - `/t/` introduce el slug del tenant — separa "qué módulo" de "qué
 *    tenant". Es obligatorio en cualquier ruta tenant-scoped.
 *  - `admin/t/` separa operación de admin del módulo. La operación es
 *    el flujo de usuario final; el admin es el de configuración por un
 *    administrador del módulo (ej. admin_sistema en GD).
 *
 * Anti-pattern: NUNCA hardcodear paths como `/t/${slug}/gd/...` en
 * componentes. Importar de acá. Si un componente quiere navegar a
 * "el buzón de GD del tenant actual", llama `gdHome(slug, '/buzon')`.
 *
 * Migración desde el esquema viejo `/t/{slug}/{module}/...` → ver
 * `legacyRedirectFor(pathname)`. Los redirects viven en el router.
 */

// =============================================================================
// Builders por módulo — uso desde componentes
// =============================================================================

/** Platform admin (no tenant). `/admin` o `/admin/tenants/...` */
export function platformAdminUrl(subPath = '') {
  return joinAdmin('/admin', subPath);
}

// ─── GD ──────────────────────────────────────────────────────────────────────

/**
 * Operación GD para un tenant. `/gd/t/{slug}` o `/gd/t/{slug}/buzon/abc`.
 *
 * @param {string} slug - Slug del tenant (no UUID).
 * @param {string} [subPath] - Sub-path relativo al módulo. Si empieza con
 *   `/admin` se redirige a `gdAdmin` para evitar URLs ambiguas.
 */
export function gdHome(slug, subPath = '') {
  assertSlug(slug, 'gdHome');
  // Defensa: `/admin/...` dentro de la operación NO existe — se promueve
  // al sub-tree de admin del módulo.
  if (subPath.startsWith('/admin')) {
    return gdAdmin(slug, subPath.replace(/^\/admin/, ''));
  }
  return joinModule(`/gd/t/${slug}`, subPath);
}

/** Admin del módulo GD para un tenant. `/gd/admin/t/{slug}/usuarios`, etc. */
export function gdAdmin(slug, subPath = '') {
  assertSlug(slug, 'gdAdmin');
  return joinModule(`/gd/admin/t/${slug}`, subPath);
}

// ─── Influencer ──────────────────────────────────────────────────────────────

export function influencerHome(slug, subPath = '') {
  assertSlug(slug, 'influencerHome');
  if (subPath.startsWith('/admin')) {
    return influencerAdmin(slug, subPath.replace(/^\/admin/, ''));
  }
  return joinModule(`/influencer/t/${slug}`, subPath);
}

export function influencerAdmin(slug, subPath = '') {
  assertSlug(slug, 'influencerAdmin');
  return joinModule(`/influencer/admin/t/${slug}`, subPath);
}

// ─── Chatbot (núcleo CopilotoIA) ─────────────────────────────────────────────

export function chatbotHome(slug, subPath = '') {
  assertSlug(slug, 'chatbotHome');
  if (subPath.startsWith('/admin')) {
    return chatbotAdmin(slug, subPath.replace(/^\/admin/, ''));
  }
  return joinModule(`/chatbot/t/${slug}`, subPath);
}

export function chatbotAdmin(slug, subPath = '') {
  assertSlug(slug, 'chatbotAdmin');
  return joinModule(`/chatbot/admin/t/${slug}`, subPath);
}

// =============================================================================
// Resolutores inversos — utilidades para componentes y middleware
// =============================================================================

/**
 * Detecta a qué módulo + modo + tenant pertenece una URL. Devuelve `null`
 * si no es una URL tenant-scoped o no encaja con el esquema.
 *
 * @param {string} pathname - Ej. `/gd/admin/t/demo/usuarios`.
 * @returns {null | { module: 'gd'|'influencer'|'chatbot',
 *                     mode: 'op'|'admin', slug: string, subPath: string }}
 */
export function parseModuleUrl(pathname) {
  if (!pathname || typeof pathname !== 'string') return null;
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length < 3) return null; // mínimo: [module, t, slug]
  const [first, second, third, ...rest] = parts;
  if (!isKnownModule(first)) return null;
  // /{module}/admin/t/{slug}/...
  if (second === 'admin' && third === 't' && parts[3]) {
    return {
      module: first, mode: 'admin', slug: parts[3],
      subPath: '/' + parts.slice(4).join('/'),
    };
  }
  // /{module}/t/{slug}/...
  if (second === 't' && third) {
    return {
      module: first, mode: 'op', slug: third,
      subPath: '/' + rest.join('/'),
    };
  }
  return null;
}

/**
 * Conversor de URLs legacy del esquema viejo `/t/{slug}/{module}/...` al
 * nuevo. Devuelve `null` si la URL no era legacy (la ruta nueva o no es
 * tenant-scoped).
 *
 * Mapeos:
 *  - `/t/{slug}` → `null` (no se redirige sola — TenantHomeRedirect elige
 *    módulo según rol).
 *  - `/t/{slug}/influencer/...` → `/influencer/t/{slug}/...`
 *  - `/t/{slug}/gd` o `/t/{slug}/gd/...` → `/gd/t/{slug}/...` o
 *    `/gd/admin/t/{slug}/...` si el sub-path empieza con `/admin`.
 *  - `/t/{slug}/read/...` → `null` (read-only shell sin migrar).
 *  - `/t/{slug}/{otro}/...` (chatbot/copiloto principal) →
 *    `/chatbot/t/{slug}/{otro}/...`.
 */
export function legacyRedirectFor(pathname) {
  if (!pathname || typeof pathname !== 'string') return null;
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length < 2 || parts[0] !== 't') return null;
  const slug = parts[1];
  if (!slug) return null;
  const moduleSegment = parts[2];
  const rest = parts.slice(3);

  // /t/{slug} sin módulo → no redirigimos; el TenantHomeRedirect del nuevo
  // esquema (acceso vía /chatbot/t/{slug}, /gd/t/{slug}, ...) maneja la home.
  if (!moduleSegment) return null;

  // /t/{slug}/read/... → no migra todavía (read-only shell aparte).
  if (moduleSegment === 'read') return null;

  // /t/{slug}/influencer/... → /influencer/t/{slug}/...
  if (moduleSegment === 'influencer') {
    return joinModule(`/influencer/t/${slug}`, '/' + rest.join('/'));
  }

  // /t/{slug}/gd o /t/{slug}/gd/... — operación o admin según subpath.
  if (moduleSegment === 'gd') {
    const sub = '/' + rest.join('/');
    if (sub.startsWith('/admin')) {
      return gdAdmin(slug, sub.replace(/^\/admin/, ''));
    }
    return gdHome(slug, sub);
  }

  // /t/{slug}/{otro}/... → chatbot (núcleo CopilotoIA).
  // El módulo legacy "tenant shell" se promueve al namespace chatbot.
  return joinModule(`/chatbot/t/${slug}`, '/' + parts.slice(2).join('/'));
}

// =============================================================================
// Constantes y helpers internos
// =============================================================================

const KNOWN_MODULES = Object.freeze(['gd', 'influencer', 'chatbot']);

export function isKnownModule(name) {
  return KNOWN_MODULES.includes(name);
}

/**
 * Patrones de rutas registrables en react-router (con `:tenantSlug`).
 * Útil para construir el array `routes` sin repetir literales.
 */
export const ROUTE_PATTERNS = Object.freeze({
  PLATFORM_ADMIN: '/admin/*',
  GD_OP:          '/gd/t/:tenantSlug/*',
  GD_ADMIN:       '/gd/admin/t/:tenantSlug/*',
  INF_OP:         '/influencer/t/:tenantSlug/*',
  INF_ADMIN:      '/influencer/admin/t/:tenantSlug/*',
  CHATBOT_OP:     '/chatbot/t/:tenantSlug/*',
  CHATBOT_ADMIN:  '/chatbot/admin/t/:tenantSlug/*',
  LEGACY_TENANT:  '/t/:tenantSlug/*',
});

// ─── internals ───────────────────────────────────────────────────────────────

function assertSlug(slug, fn) {
  if (!slug || typeof slug !== 'string') {
    throw new Error(`[urls.${fn}] slug requerido`);
  }
}

function joinModule(base, subPath) {
  if (!subPath || subPath === '/') return base;
  return base + (subPath.startsWith('/') ? subPath : '/' + subPath);
}

function joinAdmin(base, subPath) {
  if (!subPath || subPath === '/') return base;
  return base + (subPath.startsWith('/') ? subPath : '/' + subPath);
}
