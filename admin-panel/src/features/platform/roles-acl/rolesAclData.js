/**
 * UI-006.7 — Roles · ACL: pure data helpers.
 *
 * Turns the `PERMISSIONS` matrix (UI-005, `src/permissions/matrix.js`) into a
 * grouped, table-ready structure for the read-only capability × role view.
 * Kept pure so it is unit-testable without React.
 */

import { PERMISSIONS, ROLES } from '../../../permissions/index.js';

// Human label per access level. `null` cells render as the muted dash.
export const ACCESS_LABEL = {
  RW: 'R/W',
  R: 'R',
  partial: 'Parcial',
  own_only: 'Solo propio',
};

// StatusBadge tone per access level.
export const ACCESS_TONE = {
  RW: 'success',
  R: 'accent',
  partial: 'warning',
  own_only: 'warning',
};

// Human label per role (column headers).
export const ROLE_LABEL = {
  viewer: 'Viewer',
  agent: 'Agent',
  manager: 'Manager',
  admin: 'Admin',
  owner: 'Owner',
  platform_owner: 'Platform Owner',
};

// Capability domain → group label. Mirrors the section comments of matrix.js.
const _GROUP_BY_DOMAIN = {
  conversations: 'Operación diaria',
  handoff: 'Operación diaria',
  outbound_dlq: 'Operación diaria',
  appointments: 'Operación diaria',
  contacts: 'Operación diaria',
  analytics: 'Análisis y crecimiento',
  segments: 'Análisis y crecimiento',
  campaigns: 'Análisis y crecimiento',
  digest: 'Análisis y crecimiento',
  // BUG-117: nueva cap `dashboard.read` (Owner/Admin only) categorizada en
  // el mismo grupo que el resto de análisis.
  dashboard: 'Análisis y crecimiento',
  services: 'Configuración del negocio',
  packages: 'Configuración del negocio',
  subscriptions: 'Configuración del negocio',
  branches: 'Configuración del negocio',
  whatsapp: 'Canales e IA',
  social_channels: 'Canales e IA',
  knowledge: 'Canales e IA',
  knowledge_storage: 'Canales e IA',
  media: 'Canales e IA',
  tenant_setup: 'Administración del tenant',
  onboarding: 'Administración del tenant',
  team: 'Administración del tenant',
  legal: 'Administración del tenant',
  audit: 'Administración del tenant',
  go_live_readiness: 'Administración del tenant',
  platform: 'Platform Owner · fleet',
  // UI-INFLU-002: capabilities `influencer.*` agrupadas en su propia
  // sección dentro de la matriz Roles · ACL (visible en Platform Owner
  // UI-006.7). El módulo es opcional por tenant — la matriz refleja
  // el rol × acción asumiendo que el tenant tiene el módulo activo.
  influencer: 'Módulo Influencer / Ravit Studio',
};

// Stable render order for the groups.
export const GROUP_ORDER = [
  'Operación diaria',
  'Análisis y crecimiento',
  'Configuración del negocio',
  'Canales e IA',
  'Administración del tenant',
  'Módulo Influencer / Ravit Studio',
  'Platform Owner · fleet',
];

/**
 * Map a capability key (`domain.resource[.mode]`) to its group label.
 * Unknown domains fall back to 'Otros'.
 *
 * @param {string} capability
 * @returns {string}
 */
export function categorizeCapability(capability) {
  const domain = String(capability || '').split('.')[0];
  return _GROUP_BY_DOMAIN[domain] || 'Otros';
}

/**
 * Build the grouped, table-ready matrix from `PERMISSIONS`.
 *
 * @param {string} [search] optional case-insensitive capability-key filter
 * @returns {Array<{ group: string, rows: Array<{ capability: string, access: object }> }>}
 *          groups in `GROUP_ORDER`; empty groups are dropped.
 */
export function buildMatrixGroups(search = '') {
  const needle = String(search || '').trim().toLowerCase();
  const byGroup = new Map();

  for (const [capability, access] of Object.entries(PERMISSIONS)) {
    if (needle && !capability.toLowerCase().includes(needle)) continue;
    const group = categorizeCapability(capability);
    if (!byGroup.has(group)) byGroup.set(group, []);
    byGroup.get(group).push({ capability, access });
  }

  const ordered = [];
  for (const group of GROUP_ORDER) {
    const rows = byGroup.get(group);
    if (rows && rows.length > 0) {
      ordered.push({ group, rows });
    }
  }
  // Any group not in GROUP_ORDER (defensive — should not happen) goes last.
  for (const [group, rows] of byGroup) {
    if (!GROUP_ORDER.includes(group) && rows.length > 0) {
      ordered.push({ group, rows });
    }
  }
  return ordered;
}

/**
 * Count capabilities each role has any access to. Useful for the summary tiles.
 *
 * @returns {Record<string, number>} role → capability count
 */
export function countCapabilitiesPerRole() {
  const counts = {};
  for (const role of ROLES) counts[role] = 0;
  for (const access of Object.values(PERMISSIONS)) {
    for (const role of ROLES) {
      if (access[role]) counts[role] += 1;
    }
  }
  return counts;
}
