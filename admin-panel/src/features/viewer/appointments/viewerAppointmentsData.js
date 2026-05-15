/**
 * UI-010.3 — Lectura · Citas (Viewer): pure data helpers.
 *
 * Helpers para la versión read-only paginada de citas del rol Viewer. Reusa el
 * `appointmentStatusTone` del componente de dominio y los campos reales del
 * registro de cita devuelto por `listAppointments` (`starts_at`, `status`,
 * `service_name`, `resource_name`, `contact_label`). Nada de fetch — todo se
 * mantiene unit-testable sin React ni red. La única función que toca el DOM es
 * `downloadCsv` (la "export-to-CSV opcional" autorizada por el spec del
 * backlog: "solo filtros y export-to-CSV opcional"); está deliberadamente
 * pequeña para que los tests puedan espiar `URL.createObjectURL`.
 */

/**
 * Estados de cita expuestos como opciones del filtro Viewer.
 * Coinciden con los que el módulo de Agente (`todayAppointmentsData`) considera
 * canónicos y con el mapa de tonos de `AppointmentCard` (confirmed / completed
 * / pending / no_show / canceled). `rescheduled` y `cancelled` (variante con
 * doble «l») se omiten del menú de filtro porque su uso es ambiguo; el filtro
 * por status compara exactamente, así que sólo se exponen los cinco canónicos
 * del backlog.
 */
export const STATUS_FILTER_OPTIONS = Object.freeze([
  { value: 'confirmed', label: 'Confirmada' },
  { value: 'completed', label: 'Atendida' },
  { value: 'pending', label: 'Sin confirmar' },
  { value: 'no_show', label: 'No-show' },
  { value: 'canceled', label: 'Cancelada' },
]);

/** Etiqueta legible para un estado de cita (fallback: el código crudo). */
export function statusLabel(status) {
  const entry = STATUS_FILTER_OPTIONS.find((opt) => opt.value === status);
  return entry ? entry.label : status || '—';
}

/**
 * Convierte un valor (Date o string ISO) a la clave de día local `YYYY-MM-DD`.
 * Devuelve `''` cuando el valor es inválido o ausente. Pura.
 */
export function dateKey(value) {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/**
 * Devuelve la fecha + hora formateada (es-CO, dateStyle:medium, timeStyle:short)
 * para el `dateText` que recibe `AppointmentCard`. Lee del campo real
 * `starts_at`. Devuelve `'Sin fecha'` para valores inválidos.
 *
 * @param {object} appointment
 * @returns {string}
 */
export function formatDateRange(appointment) {
  const value = appointment?.starts_at;
  if (!value) return 'Sin fecha';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Sin fecha';
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

/**
 * Filtra una lista de citas en cliente por estado, rango de fechas (sobre
 * `starts_at`) y query libre contra el `contact_label` (nombre del cliente).
 *
 * Todos los criterios son opcionales: un campo vacío significa "no filtrar".
 * Para fechas, `from` y `to` son claves `YYYY-MM-DD` (locales); el rango es
 * inclusivo en ambos extremos.
 *
 * @param {object[]} appointments
 * @param {{ status?: string, from?: string, to?: string, query?: string }} filters
 * @returns {object[]}
 */
export function filterAppointments(appointments, filters = {}) {
  if (!Array.isArray(appointments)) return [];
  const status = (filters.status || '').trim();
  const from = (filters.from || '').trim();
  const to = (filters.to || '').trim();
  const query = (filters.query || '').trim().toLowerCase();

  return appointments.filter((appointment) => {
    if (status && appointment?.status !== status) return false;
    const day = dateKey(appointment?.starts_at);
    if (from && (!day || day < from)) return false;
    if (to && (!day || day > to)) return false;
    if (query) {
      const haystack = String(appointment?.contact_label || '').toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });
}

/**
 * Pagina una lista en cliente. Calcula `totalPages = max(1, ceil(total /
 * pageSize))` y clamp-ea la página al rango `[1, totalPages]`.
 *
 * @param {any[]} list
 * @param {number} page — 1-based
 * @param {number} pageSize
 * @returns {{ items: any[], page: number, pageSize: number, total: number, totalPages: number }}
 */
export function paginate(list, page, pageSize) {
  const arr = Array.isArray(list) ? list : [];
  const size = Math.max(1, Math.floor(Number(pageSize) || 1));
  const total = arr.length;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const safePage = Math.min(Math.max(1, Math.floor(Number(page) || 1)), totalPages);
  const start = (safePage - 1) * size;
  const items = arr.slice(start, start + size);
  return { items, page: safePage, pageSize: size, total, totalPages };
}

/**
 * Escapa un valor para una celda CSV: envuelve en comillas y duplica las
 * comillas internas si el valor contiene coma, comillas, salto de línea o `;`.
 * Pura.
 */
export function csvCell(value) {
  if (value === undefined || value === null) return '';
  const str = String(value);
  if (/[",;\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Serializa una lista de citas a una cadena CSV con encabezado fijo:
 * `cliente,servicio,fecha,estado,recurso`. Las filas se serializan con
 * `csvCell` para escapar comas/comillas. La fecha usa `formatDateRange`.
 *
 * @param {object[]} appointments
 * @returns {string}
 */
export function toCsv(appointments) {
  const header = ['cliente', 'servicio', 'fecha', 'estado', 'recurso'];
  const list = Array.isArray(appointments) ? appointments : [];
  const lines = [header.join(',')];
  list.forEach((appointment) => {
    const row = [
      csvCell(appointment?.contact_label || ''),
      csvCell(appointment?.service_name || appointment?.service_code || ''),
      csvCell(formatDateRange(appointment)),
      csvCell(statusLabel(appointment?.status)),
      csvCell(appointment?.resource_name || ''),
    ];
    lines.push(row.join(','));
  });
  return lines.join('\n');
}

/**
 * Dispara la descarga de una cadena CSV en el navegador creando un `Blob`
 * `text/csv;charset=utf-8` y un `<a>` temporal. Único helper impuro del
 * módulo — la "export-to-CSV opcional" autorizada por el spec del backlog
 * UI-010.3 ("solo filtros y export-to-CSV opcional"). Pequeño a propósito
 * para que los tests puedan espiar `URL.createObjectURL`.
 *
 * @param {string} csv
 * @param {string} filename
 */
export function downloadCsv(csv, filename) {
  if (typeof document === 'undefined' || typeof URL === 'undefined') return;
  const blob = new Blob([csv ?? ''], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'citas.csv';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url);
}

/** Descripción del PageHeader — surface el banner read-only y la cadencia. */
export const APPOINTMENTS_DESCRIPTION =
  'Listado paginado de citas del tenant en modo solo lectura. Filtra por estado, rango de fechas o nombre del cliente; usa "Exportar CSV" para descargar la selección actual.';
