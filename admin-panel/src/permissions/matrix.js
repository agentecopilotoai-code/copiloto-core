/**
 * Matriz de permisos UI por rol (capacidades del chrome del panel).
 *
 * Espejo defensivo de `app.role_capability` del backend: oculta/deshabilita
 * CTAs y módulos que el servidor rechazará igualmente con 403. No reemplaza
 * el chequeo del API.
 *
 * Niveles:
 *   - 'RW'  → lectura y edición.
 *   - 'R'   → solo lectura.
 *   - null  → sin acceso.
 *
 * Cada capability key es `dominio.recurso[.modo]`. Los consumidores
 * (`usePermissions().can(key, 'R'|'RW')`) deciden si renderizan, deshabilitan
 * o esconden.
 *
 * Solo capacidades del CORE (transversales). Los módulos que se instalen
 * sobre el core agregan sus propias capacidades vía un mecanismo de
 * extensión (TODO Fase 3 — module discovery con manifest.json).
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

export const PERMISSIONS = Object.freeze({
  // ─── Tenant transversales (admin del tenant en sí, no de productos) ───
  'tenant_setup.read':  { viewer: null, agent: null, manager: null, admin: R,  owner: R,  platform_owner: null },
  'tenant_setup.write': { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },
  'team.read':          { viewer: null, agent: null, manager: R,    admin: R,  owner: R,  platform_owner: null },
  'team.write':         { viewer: null, agent: null, manager: null, admin: RW, owner: RW, platform_owner: null },

  // ─── Platform Owner (fleet) ───────────────────────────────────────────
  'platform.tenants.read':         { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.tenants.write':        { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.system_health.read':   { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.billing.read':         { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.incidents.read':       { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.incidents.write':      { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.outbound_dlq.read':    { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.outbound_dlq.retry':   { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.runbooks.read':        { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.roles_acl.read':       { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.roles_acl.write':      { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.feature_flags.read':   { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.feature_flags.write':  { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  'platform.tenant_modules.read':  { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: R },
  'platform.tenant_modules.write': { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
  // Proveedores IA — config transversal cross-modalidad. Consumida por
  // cualquier módulo de producto que se instale sobre el core.
  'platform.ai_providers.configure': { viewer: null, agent: null, manager: null, admin: null, owner: null, platform_owner: RW },
});

const LEVEL_RANK = Object.freeze({ RW: 4, R: 3, own_only: 2, partial: 1 });

/**
 * Devuelve true si alguno de `roles` cubre la capability en el `mode` exigido.
 * Roles desconocidos y capabilities desconocidas → false (fail-closed).
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

export function levelFor(roles, capability) {
  const row = PERMISSIONS[capability];
  if (!row || !Array.isArray(roles)) return null;
  let best = null, bestRank = 0;
  for (const role of roles) {
    const access = row[role];
    if (!access) continue;
    const rank = LEVEL_RANK[access] || 0;
    if (rank > bestRank) { bestRank = rank; best = access; }
  }
  return best;
}

export function highestRole(roles) {
  const ORDER = ['platform_owner', 'owner', 'admin', 'manager', 'agent', 'viewer'];
  if (!Array.isArray(roles)) return 'viewer';
  for (const role of ORDER) if (roles.includes(role)) return role;
  return 'viewer';
}

/**
 * Módulo home por rol — usado por `IndexRedirect` para decidir landing.
 * `platform_owner` → fleet de tenants. Resto → `tenant-setup` (única vista
 * transversal disponible en el core; productos pueden redefinir).
 */
export const ROLE_HOME = Object.freeze({
  platform_owner: 'platform-fleet',
  owner: 'tenant-setup',
  admin: 'tenant-setup',
  manager: 'tenant-setup',
  agent: 'tenant-setup',
  viewer: 'tenant-setup',
});

const GLOBAL_ROLES = ['owner', 'platform_owner'];

/**
 * Resuelve roles efectivos en el contexto activo (con o sin tenant).
 *
 * - Sin tenant: incluye roles globales del profile (`owner`, `platform_owner`).
 * - Con tenant: incluye roles del tenant + roles globales sólo bajo
 *   `support_mode` (JWT claim o cookie temporal `supportModeOverride`
 *   matchea `tenant.id`). Si support_mode está activo y el profile tiene
 *   `platform_owner`, inyecta `owner` para que pueda operar dentro del
 *   tenant ajeno (TASK-0077 + BUG-012).
 */
export function resolveActiveRoles({ profile, tenant, supportModeOverride = null } = {}) {
  const tenantRoles = Array.isArray(tenant?.roles)
    ? tenant.roles
    : tenant?.role ? [tenant.role] : [];
  const profileRoleList = Array.isArray(profile?.roles) ? profile.roles : [];
  const profileGlobalRoles = profileRoleList.filter((r) => GLOBAL_ROLES.includes(r));

  let profileRoles;
  let injectOwner = false;
  if (!tenant) {
    profileRoles = profileGlobalRoles;
  } else {
    const overrideMatchesTenant = Boolean(
      supportModeOverride && tenant?.id
      && String(supportModeOverride.tenantId) === String(tenant.id),
    );
    const supportMode = (Boolean(profile?.support_mode) || overrideMatchesTenant)
      && profileGlobalRoles.length > 0;
    profileRoles = supportMode ? profileRoleList : [];
    injectOwner = supportMode && profileGlobalRoles.includes('platform_owner');
  }

  const finalRoles = injectOwner
    ? ['owner', ...tenantRoles, ...profileRoles]
    : [...tenantRoles, ...profileRoles];
  return Array.from(new Set(finalRoles));
}
