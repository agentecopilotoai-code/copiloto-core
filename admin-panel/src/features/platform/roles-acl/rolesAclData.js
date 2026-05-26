/**
 * Roles · ACL — pure data helpers (core).
 *
 * Turns the `PERMISSIONS` matrix into a grouped, table-ready structure for the
 * read-only capability × role view. Pure / no React.
 */

import { PERMISSIONS, ROLES } from '../../../permissions/index.js';

export const ACCESS_LABEL = {
  RW: 'R/W',
  R: 'R',
  partial: 'Parcial',
  own_only: 'Solo propio',
};

export const ACCESS_TONE = {
  RW: 'success',
  R: 'accent',
  partial: 'warning',
  own_only: 'warning',
};

export const ROLE_LABEL = {
  viewer: 'Viewer',
  agent: 'Agent',
  manager: 'Manager',
  admin: 'Admin',
  owner: 'Owner',
  platform_owner: 'Platform Owner',
};

// Capability domain → group label. En el core solo hay dos dominios:
// transversales del tenant y platform owner.
const _GROUP_BY_DOMAIN = {
  tenant_setup: 'Administración del tenant',
  team: 'Administración del tenant',
  platform: 'Platform Owner · fleet',
};

export const GROUP_ORDER = [
  'Administración del tenant',
  'Platform Owner · fleet',
];

export function categorizeCapability(capability) {
  const domain = String(capability || '').split('.')[0];
  return _GROUP_BY_DOMAIN[domain] || 'Otros';
}

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
  for (const [group, rows] of byGroup) {
    if (!GROUP_ORDER.includes(group) && rows.length > 0) {
      ordered.push({ group, rows });
    }
  }
  return ordered;
}

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
