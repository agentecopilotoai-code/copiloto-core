/**
 * UI-007.13 — Config · Equipo: pure data helpers.
 *
 * Role catalogue, role-precedence resolution, invite-form shape and the
 * role-count summary — extracted verbatim from the legacy `TeamModule` so the
 * table / invite form share them and they stay unit-testable without React.
 */

/** Role catalogue, highest privilege first. */
export const ROLE_OPTIONS = [
  { value: 'owner', label: 'Owner', description: 'Acceso total. Solo otros owners pueden asignar este rol.' },
  { value: 'admin', label: 'Admin', description: 'Configura el tenant, equipo y módulos.' },
  { value: 'manager', label: 'Manager', description: 'Operación diaria y analítica.' },
  { value: 'agent', label: 'Agent', description: 'Atiende conversaciones e inbox.' },
  { value: 'viewer', label: 'Viewer', description: 'Solo lectura.' },
];

/** Role precedence order (highest → lowest). */
export const ROLE_ORDER = ['owner', 'admin', 'manager', 'agent', 'viewer'];

/** `StatusBadge` tone per role. */
export const ROLE_TONE = {
  owner: 'accent',
  admin: 'accent',
  manager: 'success',
  agent: 'warning',
  viewer: 'neutral',
};

/** A blank invite form. */
export function emptyInviteForm() {
  return { email: '', display_name: '', role: 'agent' };
}

/** Resolve the highest-precedence role from a member's role list. */
export function highestRole(roles) {
  for (const role of ROLE_ORDER) {
    if (roles?.includes(role)) return role;
  }
  return roles?.[0] || 'viewer';
}

/** Locale-aware short date/time formatter for member timestamps. */
export function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value),
  );
}

/** Member initials for the avatar (max two letters). */
export function memberInitials(member) {
  const source = (member?.display_name || member?.email || '?').trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

/** True when the caller can assign/manage the `owner` role. */
export function callerIsOwner(profileRoles, tenantRoles) {
  const roles = new Set([...(profileRoles || []), ...(tenantRoles || [])]);
  return roles.has('owner') || roles.has('platform_owner');
}

/** Count of members per role (by highest role) + pending invitations. */
export function roleCounts(members) {
  const counts = { owner: 0, admin: 0, manager: 0, agent: 0, viewer: 0, pending: 0 };
  (members || []).forEach((member) => {
    counts[highestRole(member.roles)] += 1;
    if (member.status === 'invited') counts.pending += 1;
  });
  return counts;
}
