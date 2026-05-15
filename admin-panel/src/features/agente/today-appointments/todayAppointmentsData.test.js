import { describe, it, expect } from 'vitest';

import {
  dateKey,
  deriveCounts,
  filterByDay,
  groupByStatus,
  nextAppointment,
  shiftDayISO,
  sortByTime,
  statusLabel,
  statusTone,
  todayISO,
} from './todayAppointmentsData.js';

const DAY = '2026-05-14';
const APPTS = [
  { id: 'a', starts_at: '2026-05-14T11:00:00Z', status: 'confirmed' },
  { id: 'b', starts_at: '2026-05-14T09:00:00Z', status: 'completed' },
  { id: 'c', starts_at: '2026-05-14T10:00:00Z', status: 'pending' },
  { id: 'd', starts_at: '2026-05-15T09:00:00Z', status: 'confirmed' },
  { id: 'e', starts_at: '2026-05-14T14:00:00Z', status: 'rescheduled' },
];

describe('todayAppointmentsData', () => {
  it('dateKey + shiftDayISO derive local day keys', () => {
    expect(dateKey('2026-05-14T11:00:00Z')).toMatch(/^2026-05-1[34]$/);
    expect(dateKey('not-a-date')).toBe('');
    expect(dateKey('')).toBe('');
    expect(shiftDayISO(DAY, 1)).toBe('2026-05-15');
    expect(shiftDayISO(DAY, -1)).toBe('2026-05-13');
    expect(todayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('filterByDay keeps only appointments whose starts_at falls on the day', () => {
    // Use a day computed from the records so timezone offset can't break it.
    const day = dateKey(APPTS[0].starts_at);
    const sameDay = APPTS.filter((a) => dateKey(a.starts_at) === day);
    const filtered = filterByDay(APPTS, day);
    expect(filtered).toHaveLength(sameDay.length);
    expect(filtered.every((a) => dateKey(a.starts_at) === day)).toBe(true);
    expect(filterByDay(APPTS, '')).toEqual([]);
    expect(filterByDay(null, day)).toEqual([]);
  });

  it('sortByTime orders ascending by starts_at without mutating', () => {
    const input = filterByDay(APPTS, dateKey(APPTS[0].starts_at));
    const sorted = sortByTime(input);
    const times = sorted.map((a) => new Date(a.starts_at).getTime());
    expect(times).toEqual([...times].sort((x, y) => x - y));
    expect(input).not.toBe(sorted);
  });

  it('deriveCounts derives total, unconfirmed and attended counts', () => {
    const day = dateKey(APPTS[0].starts_at);
    const counts = deriveCounts(filterByDay(APPTS, day));
    // b completed, a confirmed, c pending, e rescheduled all land on the same day.
    expect(counts.total).toBe(4);
    expect(counts.unconfirmed).toBe(2); // pending + rescheduled
    expect(counts.attended).toBe(1); // completed
  });

  it('nextAppointment returns the first future appointment by time', () => {
    const day = dateKey(APPTS[0].starts_at);
    const list = filterByDay(APPTS, day);
    const before = new Date('2026-05-14T08:00:00Z');
    expect(nextAppointment(list, before)?.starts_at).toBe('2026-05-14T09:00:00Z');
    const after = new Date('2026-05-14T23:00:00Z');
    expect(nextAppointment(list, after)).toBeNull();
  });

  it('groupByStatus, statusLabel and statusTone map statuses', () => {
    const groups = groupByStatus(APPTS);
    expect(groups.confirmed).toHaveLength(2);
    expect(groups.pending).toHaveLength(1);
    expect(statusLabel('no_show')).toBe('No-show');
    expect(statusLabel('completed')).toBe('Atendida');
    expect(statusLabel('weird')).toBe('weird');
    expect(statusTone('confirmed')).toBe('success');
    expect(statusTone('no_show')).toBe('danger');
    expect(statusTone('pending')).toBe('warning');
  });
});
