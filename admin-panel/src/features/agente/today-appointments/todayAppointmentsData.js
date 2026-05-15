/**
 * UI-009.5 — Hoy · Citas del día: helpers puros.
 *
 * Constantes, formatters y derivaciones de conteo para la vista de citas del
 * día del rol Agente. Sin React — todo unit-testable. El filtro por día corre
 * en cliente: `listAppointments` no expone un parámetro de fecha establecido en
 * el frontend (ver `useScheduleData` que lo llama sin filtros), así que se
 * filtra la lista completa sobre el campo real `starts_at`.
 */

import { appointmentStatusTone } from '../../../components/domain/index.js';

/** Etiquetas en español por estado de cita. */
export const STATUS_LABELS = Object.freeze({
  confirmed: 'Confirmada',
  pending: 'Sin confirmar',
  completed: 'Atendida',
  no_show: 'No-show',
  rescheduled: 'Reprogramada',
  canceled: 'Cancelada',
  cancelled: 'Cancelada',
});

/** Etiqueta legible para un estado de cita (fallback: el código crudo). */
export function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—';
}

/** Tono de `StatusBadge` para un estado de cita (reusa el mapa del dominio). */
export function statusTone(status) {
  return appointmentStatusTone(status);
}

/** Fecha de hoy como `YYYY-MM-DD` en hora local. */
export function todayISO() {
  return dateKey(new Date());
}

/**
 * Clave de día `YYYY-MM-DD` (hora local) de una fecha o string ISO.
 * Devuelve `''` cuando el valor es inválido o ausente.
 */
export function dateKey(value) {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** Desplaza una clave de día `YYYY-MM-DD` en `delta` días (local). */
export function shiftDayISO(dayISO, delta) {
  const base = dayISO ? new Date(`${dayISO}T00:00:00`) : new Date();
  if (Number.isNaN(base.getTime())) return todayISO();
  base.setDate(base.getDate() + delta);
  return dateKey(base);
}

/**
 * Filtra las citas cuyo `starts_at` cae en el día `dayISO` (`YYYY-MM-DD`).
 * El campo de fecha real de un registro de cita es `starts_at` (ver
 * `inbox/components/contact-panel/ContactScheduleSection.jsx` y
 * `useScheduleData`). Filtro en cliente: sin parámetro de servidor inventado.
 */
export function filterByDay(appointments, dayISO) {
  if (!Array.isArray(appointments) || !dayISO) return [];
  return appointments.filter((appointment) => dateKey(appointment?.starts_at) === dayISO);
}

/** Ordena ascendente por hora de inicio (`starts_at`); estable, no muta. */
export function sortByTime(appointments) {
  if (!Array.isArray(appointments)) return [];
  return [...appointments].sort((a, b) => {
    const ta = new Date(a?.starts_at || 0).getTime();
    const tb = new Date(b?.starts_at || 0).getTime();
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb);
  });
}

/** Etiqueta de hora `HH:MM` (es-CO) de un `starts_at`; `—` si es inválido. */
export function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('es-CO', { hour: '2-digit', minute: '2-digit' }).format(date);
}

/** Fecha + hora larga (es-CO) para el `dateText` de `AppointmentCard`. */
export function formatDateTime(value) {
  if (!value) return 'Sin fecha';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Sin fecha';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

/** Etiqueta del navegador de día: `Hoy · 14 may` / fecha media para otros días. */
export function dayNavLabel(dayISO) {
  if (!dayISO) return '—';
  const date = new Date(`${dayISO}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dayISO;
  const pretty = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short' }).format(date);
  if (dayISO === todayISO()) return `Hoy · ${pretty}`;
  if (dayISO === shiftDayISO(todayISO(), 1)) return `Mañana · ${pretty}`;
  if (dayISO === shiftDayISO(todayISO(), -1)) return `Ayer · ${pretty}`;
  return pretty;
}

/** Estados que cuentan como "sin confirmar" para el KPI homónimo. */
const UNCONFIRMED_STATUSES = ['pending', 'rescheduled'];
/** Estados que cuentan como "atendida". */
const ATTENDED_STATUSES = ['completed'];

/** Agrupa citas por estado: `{ [status]: Appointment[] }`. */
export function groupByStatus(appointments) {
  const groups = {};
  if (!Array.isArray(appointments)) return groups;
  appointments.forEach((appointment) => {
    const status = appointment?.status || 'unknown';
    if (!groups[status]) groups[status] = [];
    groups[status].push(appointment);
  });
  return groups;
}

/**
 * Próxima cita futura del día (la primera con `starts_at >= now`, ordenadas por
 * hora). `now` es inyectable para tests. Devuelve `null` si no hay ninguna.
 */
export function nextAppointment(appointments, now = new Date()) {
  const nowMs = now instanceof Date ? now.getTime() : new Date(now).getTime();
  return (
    sortByTime(appointments).find((appointment) => {
      const ts = new Date(appointment?.starts_at || 0).getTime();
      return !Number.isNaN(ts) && ts >= nowMs;
    }) || null
  );
}

/**
 * Conteos derivables de la lista de citas del día: total, sin confirmar,
 * atendidas y la próxima cita. Solo campos reales del registro de cita.
 */
export function deriveCounts(appointments, now = new Date()) {
  const list = Array.isArray(appointments) ? appointments : [];
  const unconfirmed = list.filter((a) => UNCONFIRMED_STATUSES.includes(a?.status)).length;
  const attended = list.filter((a) => ATTENDED_STATUSES.includes(a?.status)).length;
  return {
    total: list.length,
    unconfirmed,
    attended,
    next: nextAppointment(list, now),
  };
}
