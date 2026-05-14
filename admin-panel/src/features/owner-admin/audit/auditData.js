/**
 * UI-007.15 — Config · Auditoría: pure data helpers.
 *
 * Filter-form shape, the filter → API payload mapping, the actor-type catalogue
 * and the static DPA policy summary — extracted verbatim from the legacy
 * `AuditPanel` so the filters / table / privacy panels share them and they stay
 * unit-testable without React.
 */

/** Actor-type options for the audit-log filter. */
export const ACTOR_TYPE_OPTIONS = [
  { value: 'user', label: 'user' },
  { value: 'agent', label: 'agent' },
  { value: 'bot', label: 'bot' },
  { value: 'service', label: 'service' },
  { value: 'system', label: 'system' },
  { value: 'support', label: 'support' },
  { value: 'contact', label: 'contact' },
];

/** A blank audit-log filter form. */
export function emptyFilters() {
  return {
    action: '',
    actorType: '',
    entityType: '',
    fromDate: '',
    toDate: '',
    limit: '200',
  };
}

/**
 * Map the filter form onto the API query payload — empty fields become
 * `undefined` so they drop out of the query string. `includeLimit` is `false`
 * for the CSV export (which has no limit), `true` for the list query.
 */
export function buildFilterPayload(filters, { includeLimit = true } = {}) {
  const payload = {
    action: filters.action || undefined,
    actor_type: filters.actorType || undefined,
    entity_type: filters.entityType || undefined,
    from_date: filters.fromDate || undefined,
    to_date: filters.toDate || undefined,
  };
  if (includeLimit) payload.limit = filters.limit || '200';
  return payload;
}

/** Locale-aware short date/time formatter for audit-log timestamps. */
export function formatDate(value) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value),
  );
}

/**
 * Data Processing Agreement summary, surfaced read-only in the panel.
 * Mirrors the legacy DPA list verbatim.
 */
export const DPA_POLICY = [
  {
    title: 'No entrenamiento',
    body: 'Los datos de conversaciones nunca se usan para entrenar modelos de IA. El campo no_train del tenant es true por defecto.',
  },
  {
    title: 'Retención',
    body: 'Los datos operativos se retienen máximo 365 días desde la última actividad del tenant. Los audit logs se conservan 730 días para cumplimiento.',
  },
  {
    title: 'PII en logs',
    body: 'Los logs de sistema redactan automáticamente teléfonos y correos antes de persistirlos.',
  },
  {
    title: 'Derecho al olvido',
    body: 'La supresión de contacto anonimiza datos personales de forma irreversible en menos de 24 horas desde la solicitud.',
  },
  {
    title: 'Procesador de datos',
    body: 'CopilotoIA actúa como encargado del tratamiento; el tenant es el responsable. Ver docs/DPA.md para el texto completo.',
  },
];
