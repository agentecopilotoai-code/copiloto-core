/**
 * UI-016.1 — agrupación de checks de go-live en secciones visuales.
 *
 * El backend (`getTenantReadiness`) devuelve un array plano de `checks`, cada
 * uno con una `key`. El HTML del diseñador agrupa esos checks en 5 secciones
 * temáticas (Tenant activo, Canal WhatsApp y templates, Retrieval y políticas,
 * Operación y handoff, Cobranza y plan). Este mapping decide a qué sección va
 * cada `check.key`; cuando aparezca una key nueva no mapeada, cae a la sección
 * "general" (fail-soft) para que UI-016.1 nunca esconda un check del backend.
 */

export const SECTION_ORDER = [
  'tenant',
  'whatsapp',
  'retrieval',
  'operations',
  'billing',
  'general',
];

export const SECTION_META = Object.freeze({
  tenant: {
    id: 'tenant',
    title: 'Tenant activo y configurado',
    keys: ['tenant_active', 'tenant_settings'],
  },
  whatsapp: {
    id: 'whatsapp',
    title: 'Canal WhatsApp y templates',
    keys: ['whatsapp_channel', 'whatsapp_template', 'whatsapp_quality'],
  },
  retrieval: {
    id: 'retrieval',
    title: 'Retrieval y políticas',
    keys: ['knowledge_retrieval', 'retention_policy', 'legal_endpoint', 'policy_engine'],
  },
  operations: {
    id: 'operations',
    title: 'Operación y handoff',
    keys: ['team_mfa', 'handoff', 'audit'],
  },
  billing: {
    id: 'billing',
    title: 'Cobranza y plan',
    keys: ['payment_method', 'subscription', 'test_charge'],
  },
  general: {
    id: 'general',
    title: 'Otros checks',
    keys: [],
  },
});

const KEY_TO_SECTION = (() => {
  const map = new Map();
  for (const section of Object.values(SECTION_META)) {
    for (const key of section.keys) {
      map.set(key, section.id);
    }
  }
  return map;
})();

/**
 * Convierte el `report.checks` plano en `{ section, checks, passed, total }[]`,
 * preservando el orden declarativo de `SECTION_ORDER` (vacías se omiten).
 *
 * @param {Array<{key:string, ready:boolean, label:string, reason?:string, details?:object}>} checks
 */
export function groupChecksBySection(checks) {
  const buckets = new Map();
  for (const check of checks || []) {
    const sectionId = KEY_TO_SECTION.get(check.key) || 'general';
    if (!buckets.has(sectionId)) buckets.set(sectionId, []);
    buckets.get(sectionId).push(check);
  }
  const result = [];
  for (const sectionId of SECTION_ORDER) {
    const sectionChecks = buckets.get(sectionId);
    if (!sectionChecks || sectionChecks.length === 0) continue;
    const passed = sectionChecks.filter((c) => c.ready).length;
    result.push({
      section: SECTION_META[sectionId],
      checks: sectionChecks,
      passed,
      total: sectionChecks.length,
    });
  }
  return result;
}

/**
 * Stringify de `check.details` para el rendering (lista breve `key: value · …`).
 * Mantenida fuera del componente para test directo.
 */
export function formatCheckDetails(details) {
  if (!details || typeof details !== 'object') return '';
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 4)
    .map(([key, value]) => {
      const valueStr = typeof value === 'object' ? JSON.stringify(value) : String(value);
      return `${key}: ${valueStr}`;
    })
    .join(' · ');
}

/**
 * Construye el contenido CSV (UTF-8 con BOM) del checklist para descarga
 * client-side. Cada fila es `seccion,check,estado,detalle`.
 *
 * @param {Array<ReturnType<typeof groupChecksBySection>[number]>} grouped
 * @param {object} report Reporte completo (`{ tenant_id, ready, checked_at, ... }`).
 */
export function buildChecklistCsv(grouped, report) {
  const lines = ['seccion,check,estado,detalle'];
  for (const { section, checks } of grouped) {
    for (const check of checks) {
      const reason = (check.reason || '').replace(/"/g, '""');
      const seccion = section.title.replace(/"/g, '""');
      const label = (check.label || '').replace(/"/g, '""');
      const estado = check.ready ? 'OK' : 'PENDIENTE';
      lines.push(`"${seccion}","${label}",${estado},"${reason}"`);
    }
  }
  const meta = [
    `# tenant_id=${report?.tenant_id || ''}`,
    `# checked_at=${report?.checked_at || ''}`,
    `# ready=${report?.ready ? 'true' : 'false'}`,
  ];
  // UTF-8 BOM para que Excel detecte UTF-8.
  return '﻿' + meta.join('\n') + '\n' + lines.join('\n');
}
