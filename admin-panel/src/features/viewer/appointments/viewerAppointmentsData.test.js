import { describe, it, expect } from 'vitest';

import {
  STATUS_FILTER_OPTIONS,
  csvCell,
  dateKey,
  filterAppointments,
  formatDateRange,
  paginate,
  statusLabel,
  toCsv,
} from './viewerAppointmentsData.js';

const APPTS = [
  {
    id: 'a',
    starts_at: '2026-05-14T11:00:00Z',
    status: 'confirmed',
    service_name: 'Botox frontal',
    resource_name: 'Dra. Sofía',
    contact_label: 'María José L.',
  },
  {
    id: 'b',
    starts_at: '2026-05-15T09:00:00Z',
    status: 'completed',
    service_name: 'Peeling',
    resource_name: 'Dra. Sofía',
    contact_label: 'Andrés Gómez',
  },
  {
    id: 'c',
    starts_at: '2026-05-16T10:00:00Z',
    status: 'scheduled',
    service_name: 'Limpieza facial · paquete',
    resource_name: 'Dra. Laura',
    contact_label: 'Diego Castro',
  },
  {
    id: 'd',
    starts_at: '2026-05-17T14:00:00Z',
    status: 'no_show',
    service_name: 'Botox · VIP',
    resource_name: 'Dra. Sofía',
    contact_label: 'Sofía Quintero',
  },
  {
    id: 'e',
    starts_at: '2026-05-18T08:00:00Z',
    status: 'cancelled',
    service_name: 'Anti-edad',
    resource_name: 'Dra. Laura',
    contact_label: 'Laura Martínez',
  },
];

describe('viewerAppointmentsData', () => {
  it('STATUS_FILTER_OPTIONS expone los cinco estados canónicos del schema', () => {
    // BUG-099 fix: alineados con el enum del schema
    // (`app.appointments.status CHECK in
    // (scheduled, confirmed, completed, cancelled, no_show)`).
    // Antes el filtro exponía `pending` (que el backend no tiene) y
    // `canceled` (una sola L; backend `cancelled` con doble L) —
    // ninguna cita matcheaba esos valores y el filter siempre devolvía 0.
    expect(STATUS_FILTER_OPTIONS.map((opt) => opt.value)).toEqual([
      'scheduled',
      'confirmed',
      'completed',
      'cancelled',
      'no_show',
    ]);
    expect(statusLabel('no_show')).toBe('No-show');
    expect(statusLabel('weird')).toBe('weird');
  });

  it('filterAppointments filtra por estado, rango de fechas y query de cliente', () => {
    // status sólo (BUG-099: usar el enum canónico del schema).
    expect(filterAppointments(APPTS, { status: 'scheduled' }).map((a) => a.id)).toEqual(['c']);

    // rango de fechas (inclusivo) — usamos el `dateKey` real para evitar romper
    // el test por la zona horaria del runner.
    const day14 = dateKey(APPTS[0].starts_at);
    const day16 = dateKey(APPTS[2].starts_at);
    const inRange = filterAppointments(APPTS, { from: day14, to: day16 });
    expect(inRange.length).toBeGreaterThanOrEqual(1);
    expect(inRange.every((a) => dateKey(a.starts_at) >= day14 && dateKey(a.starts_at) <= day16)).toBe(true);

    // query libre contra el contact_label (case-insensitive, substring)
    expect(filterAppointments(APPTS, { query: 'andrés' }).map((a) => a.id)).toEqual(['b']);
    expect(filterAppointments(APPTS, { query: 'maría' }).map((a) => a.id)).toEqual(['a']);

    // input inválido devuelve lista vacía
    expect(filterAppointments(null, {})).toEqual([]);
  });

  it('paginate respeta tamaño de página y clamp-ea la página al rango válido', () => {
    const list = [1, 2, 3, 4, 5, 6, 7];

    const firstPage = paginate(list, 1, 3);
    expect(firstPage.items).toEqual([1, 2, 3]);
    expect(firstPage.page).toBe(1);
    expect(firstPage.totalPages).toBe(3);
    expect(firstPage.total).toBe(7);

    const lastPage = paginate(list, 3, 3);
    expect(lastPage.items).toEqual([7]);

    // página fuera de rango (por encima) → clamp a la última.
    const clampedHigh = paginate(list, 99, 3);
    expect(clampedHigh.page).toBe(3);
    expect(clampedHigh.items).toEqual([7]);

    // página fuera de rango (por debajo) → clamp a la primera.
    const clampedLow = paginate(list, 0, 3);
    expect(clampedLow.page).toBe(1);
    expect(clampedLow.items).toEqual([1, 2, 3]);

    // lista vacía → totalPages = 1, items = [].
    const empty = paginate([], 1, 5);
    expect(empty.total).toBe(0);
    expect(empty.totalPages).toBe(1);
    expect(empty.items).toEqual([]);
  });

  it('csvCell escapa comas, comillas y saltos de línea', () => {
    expect(csvCell('plain')).toBe('plain');
    expect(csvCell('with, comma')).toBe('"with, comma"');
    expect(csvCell('with "quotes"')).toBe('"with ""quotes"""');
    expect(csvCell('line\nbreak')).toBe('"line\nbreak"');
    expect(csvCell(null)).toBe('');
    expect(csvCell(undefined)).toBe('');
  });

  it('toCsv produce header + una fila por cita con los campos esperados', () => {
    const csv = toCsv([APPTS[0], APPTS[1]]);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('cliente,servicio,fecha,estado,recurso');
    expect(lines).toHaveLength(3);

    // Línea 1: María José L. (la fecha formateada incluye coma → la celda se
    // envuelve en comillas por csvCell; estado se mapea por statusLabel).
    expect(lines[1]).toContain('María José L.');
    expect(lines[1]).toContain('Botox frontal');
    expect(lines[1]).toContain('Confirmada');
    expect(lines[1]).toContain('Dra. Sofía');
  });

  it('formatDateRange formatea starts_at y degrada elegante si falta', () => {
    expect(formatDateRange({ starts_at: '2026-05-14T11:00:00Z' })).toMatch(/\d/);
    expect(formatDateRange({})).toBe('Sin fecha');
    expect(formatDateRange({ starts_at: 'not-a-date' })).toBe('Sin fecha');
  });
});
