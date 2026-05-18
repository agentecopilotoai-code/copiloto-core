/**
 * Matriz de permisos UI por rol.
 *
 * Fuente: `docs/HTML DESIGN/00 _ Documentaci_n de acceso.png`
 *         + sección 2 de `docs/UI_BACKLOG.md`
 *         + screens declaradas en sección 0.bis.3 (mapping rol ↔ pantalla).
 *
 * El servidor enforce JWT + role + RLS por endpoint (TASK-0001/0016/0077/0080).
 * Esta matriz es el espejo defensivo de la UI: oculta/deshabilita CTAs y módulos
 * que el servidor rechazará igualmente con 403. No reemplaza el chequeo del API.
 *
 * Niveles de acceso por celda:
 *   - 'RW'        → lectura y edición.
 *   - 'R'         → solo lectura.
 *   - 'partial'   → subset acotado (ej. contactos: agente puede editar tags pero
 *                   no PII).
 *   - 'own_only'  → scope limitado a su trabajo (ej. agent.performance: el agente
 *                   ve sólo sus métricas).
 *   - null        → sin acceso (`—` en la matriz).
 *
 * Cada capability key es un string `dominio.recurso[.modo]`. Los consumidores
 * (`usePermissions().can(key, 'R'|'RW')`) deciden si renderizan, deshabilitan o
 * esconden. Para extender la matriz, agregar la capability al objeto y a los
 * tests en `matrix.test.js`.
 */

export const ROLES = Object.freeze([
  'viewer',
  'agent',
  'manager',
  'admin',
  'owner',
  'platform_owner',
]);

const RW = 'RW';
const R = 'R';
const PARTIAL = 'partial';
const OWN = 'own_only';

export const PERMISSIONS = Object.freeze({
  // ─────────────────────────────────── OPERACIÓN DIARIA ───────────────────────────────────
  'conversations.view':        { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'handoff.take':              { viewer: null, agent: RW,   manager: RW, admin: RW, owner: RW, platform_owner: null },
  'outbound_dlq.retry':        { viewer: null, agent: RW,   manager: RW, admin: RW, owner: RW, platform_owner: null },
  'appointments.view':         { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'appointments.write':        { viewer: null, agent: RW,   manager: RW, admin: RW, owner: RW, platform_owner: null },
  'contacts.view':             { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'contacts.write':            { viewer: null, agent: PARTIAL, manager: RW, admin: RW, owner: RW, platform_owner: null },

  // ─────────────────────────────────── ANÁLISIS Y CRECIMIENTO ───────────────────────────────
  'analytics.tenant.read':     { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'analytics.agent_performance.read': { viewer: null, agent: OWN, manager: R, admin: R, owner: R, platform_owner: null },
  'segments.read':             { viewer: null, agent: null, manager: R,  admin: R,  owner: R,  platform_owner: null },
  'segments.write':            { viewer: null, agent: null, manager: RW, admin: RW, owner: RW, platform_owner: null },
  'campaigns.read':            { viewer: null, agent: null, manager: R,  admin: R,  owner: R,  platform_owner: null },
  'campaigns.write':           { viewer: null, agent: null, manager: RW, admin: RW, owner: RW, platform_owner: null },
  'digest.write':              { viewer: null, agent: null, manager: RW, admin: RW, owner: RW, platform_owner: null },

  // ─────────────────────────────────── CONFIGURACIÓN DEL NEGOCIO ───────────────────────────
  'services.read':             { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'services.write':            { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'packages.write':            { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'subscriptions.write':       { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'branches.write':            { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },

  // ─────────────────────────────────── CANALES E IA ────────────────────────────────────────
  'whatsapp.read':             { viewer: null, agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'whatsapp.write':            { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'social_channels.write':     { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'knowledge.read':            { viewer: null, agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'knowledge.write':           { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'knowledge_storage.write':   { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'media.read':                { viewer: null, agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'media.write':               { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },

  // ─────────────────────────────────── ADMINISTRACIÓN DEL TENANT ──────────────────────────
  'tenant_setup.read':         { viewer: null, agent: null, manager: null, admin: R,  owner: R,  platform_owner: null },
  'tenant_setup.write':        { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'onboarding.run':            { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'team.read':                 { viewer: null, agent: null, manager: R,  admin: R,  owner: R,  platform_owner: null },
  'team.write':                { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'legal.read':                { viewer: R,    agent: R,    manager: R,  admin: R,  owner: R,  platform_owner: null },
  'legal.write':               { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'audit.read':                { viewer: null, agent: null, manager: null, admin: R,  owner: R,  platform_owner: null },
  'go_live_readiness.read':    { viewer: null, agent: null, manager: null, admin: R,  owner: R,  platform_owner: null },
  'go_live_readiness.mark_live': { viewer: null, agent: null, manager: null, admin: null, owner: RW, platform_owner: null },

  // ─────────────────────────────────── PLATFORM OWNER (fleet) ─────────────────────────────
  'platform.tenants.read':       { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.tenants.write':      { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.system_health.read': { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.billing.read':       { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.incidents.read':     { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.incidents.write':    { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.outbound_dlq.read':  { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.outbound_dlq.retry': { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.runbooks.read':      { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.roles_acl.read':     { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.roles_acl.write':    { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.feature_flags.read': { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.feature_flags.write':{ viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
});

const LEVEL_RANK = Object.freeze({
  RW: 4,
  R: 3,
  own_only: 2,
  partial: 1,
});

/**
 * Devuelve true si alguno de `roles` cubre la capability en el `mode` exigido.
 *
 * - `mode='R'`  (default): cualquier acceso (`R`, `RW`, `partial`, `own_only`) cuenta.
 * - `mode='RW'`: solo `RW` cuenta.
 *
 * Roles desconocidos y capabilities desconocidas → `false` (fail-closed).
 */
export function can(roles, capability, mode = 'R') {
  const row = PERMISSIONS[capability];
  if (!row) return false;
  if (!Array.isArray(roles) || roles.length === 0) return false;
  for (const role of roles) {
    const access = row[role];
    if (!access) continue;
    if (mode === 'RW') {
      if (access === 'RW') return true;
    } else {
      return true;
    }
  }
  return false;
}

/**
 * Devuelve el nivel de acceso más fuerte (`'RW' > 'R' > 'own_only' > 'partial'`)
 * que `roles` tienen para `capability`. `null` si no hay acceso.
 */
export function levelFor(roles, capability) {
  const row = PERMISSIONS[capability];
  if (!row) return null;
  if (!Array.isArray(roles)) return null;
  let bestLevel = null;
  let bestRank = 0;
  for (const role of roles) {
    const access = row[role];
    if (!access) continue;
    const rank = LEVEL_RANK[access] || 0;
    if (rank > bestRank) {
      bestRank = rank;
      bestLevel = access;
    }
  }
  return bestLevel;
}

/**
 * Rol más alto presente en `roles`. Devuelve `'viewer'` si la lista está vacía.
 * Útil para decidir landing (`ROLE_HOME`) y default UI.
 */
export function highestRole(roles) {
  const ORDER = ['platform_owner', 'owner', 'admin', 'manager', 'agent', 'viewer'];
  if (!Array.isArray(roles)) return 'viewer';
  for (const role of ORDER) {
    if (roles.includes(role)) return role;
  }
  return 'viewer';
}

/**
 * Module ID por defecto para cada rol (sección 6 del UI_BACKLOG).
 * Consumido por el shell para decidir landing al entrar.
 */
export const ROLE_HOME = Object.freeze({
  platform_owner: 'platform-fleet',
  owner: 'dashboard',
  admin: 'dashboard',
  manager: 'manager-analytics',
  agent: 'operations-desk',
  viewer: 'viewer-summary',
});

/**
 * Resuelve los roles efectivos que aplican en el contexto activo.
 *
 * Hay DOS contextos distintos y se tratan diferente para no mezclar capas:
 *
 *   1. **Sin tenant activo** (`tenant === null`): el caller está mirando vistas
 *      globales de la plataforma (ej. `/platform/*`, decidir el redirect inicial
 *      en `IndexRedirect`). Acá los roles globales del profile (`owner`,
 *      `platform_owner`) aplican SIEMPRE — no requieren support_mode. Un
 *      platform_owner siempre debe poder ver sus propias vistas, sea o no que
 *      esté operando en algún tenant en particular. Sin esto, BUG-006 reaparece:
 *      el `IndexRedirect` no detecta el rol global y manda al usuario al
 *      onboarding de tenant en vez de a `/platform`.
 *
 *   2. **Con tenant activo** (`tenant !== null`): el caller está operando
 *      DENTRO de un tenant concreto. Acá rige TASK-0077: los roles globales
 *      solo se suman al merge si `support_mode === true` y el profile tiene
 *      rol `owner`/`platform_owner`. Esto previene que un platform_owner opere
 *      accidentalmente en un tenant ajeno con privilegios elevados sin haber
 *      activado support_mode a propósito (espejo del backend).
 *
 * BUG-008 — `supportModeOverride` agrega una tercera fuente de support_mode
 * en el contexto de tenant: si el `TenantProvider` activó el toggle
 * temporal (cookie scoped server-side) Y el `tenantId` del override matchea
 * el tenant activo, OR-eamos con `profile.support_mode` del JWT. El backend
 * tiene su propio gating (cookie + matcheo con `X-Tenant-Id` en
 * `authenticate_request`), así que este flag de frontend solo afecta lo
 * que la UI muestra/oculta — los writes igual van a tener que pasar el
 * gate del servidor.
 *
 * Roles de tenant (`tenant.roles` / `tenant.role` legacy) se incluyen siempre.
 * Devuelve un array deduplicado. Si nada aplica → `[]` (fail-closed).
 */
const GLOBAL_ROLES = ['owner', 'platform_owner'];

export function resolveActiveRoles({ profile, tenant, supportModeOverride = null } = {}) {
  const tenantRoles = Array.isArray(tenant?.roles)
    ? tenant.roles
    : tenant?.role
      ? [tenant.role]
      : [];

  const profileRoleList = Array.isArray(profile?.roles) ? profile.roles : [];
  const profileGlobalRoles = profileRoleList.filter((r) => GLOBAL_ROLES.includes(r));

  let profileRoles;
  let injectOwnerForSupportMode = false;
  if (!tenant) {
    // Contexto global (sin tenant): siempre incluir los roles globales del
    // profile. BUG-006: sin esto, platform_owner cae al onboarding de tenant.
    profileRoles = profileGlobalRoles;
  } else {
    // Contexto de tenant: TASK-0077 + BUG-008 — profile.roles se sumarn al
    // merge si CUALQUIERA de las dos fuentes de support_mode aplica:
    //   * `profile.support_mode` del JWT (modo permanente — workaround legacy).
    //   * `supportModeOverride.tenantId === tenant.id` (opt-in temporal vía
    //     POST /v1/me/support-mode/{tenant_id}; el backend valida el cookie
    //     y bumpea su propio request.state.support_mode).
    // En ambos casos requerimos que el profile tenga un rol global —
    // support_mode sin rol global es inocuo (no escala nada).
    const overrideMatchesTenant = Boolean(
      supportModeOverride
      && tenant?.id
      && String(supportModeOverride.tenantId) === String(tenant.id),
    );
    const supportMode =
      (Boolean(profile?.support_mode) || overrideMatchesTenant)
      && profileGlobalRoles.length > 0;
    profileRoles = supportMode ? profileRoleList : [];
    // BUG-012: cuando support_mode está activo el platform_owner espera tener
    // acceso completo al tenant (admin/owner-equivalent) — ese es el propósito
    // del feature. Pero la matriz tiene `platform_owner: null` para TODAS las
    // capabilities tenant-scoped (`tenant_setup.write`, `team.write`, etc.)
    // porque `platform_owner` es fleet-wide, no tenant. Sin inyectar `'owner'`
    // acá, el platform_owner en support_mode ve el banner "tenés acceso
    // temporal" pero al clickear cualquier módulo admin recibe "Acceso
    // restringido". El feature pierde su propósito.
    // Inyectamos `'owner'` solo cuando: (1) support_mode está activo (no
    // relaja el permission model en flujos normales) Y (2) el profile tiene
    // `platform_owner` global (un `owner` sin `platform_owner` no debería
    // poder elevarse a owner de OTRO tenant — `overrideMatchesTenant` ya
    // gatea esto, pero defense en profundidad).
    injectOwnerForSupportMode =
      supportMode && profileGlobalRoles.includes('platform_owner');
  }

  const finalRoles = injectOwnerForSupportMode
    ? ['owner', ...tenantRoles, ...profileRoles]
    : [...tenantRoles, ...profileRoles];
  return Array.from(new Set(finalRoles));
}
