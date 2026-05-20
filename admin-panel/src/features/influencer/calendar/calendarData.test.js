import { describe, it, expect } from 'vitest';

import {
  buildSchedulePayload,
  canApprove,
  formatTimeSlot,
  groupPostsByDay,
  personaColorMap,
  weekRange,
} from './calendarData.js';


describe('calendarData (UI-INFLU-014)', () => {
  it('weekRange devuelve lunes a domingo + label es-CO', () => {
    const wed = new Date('2026-05-13T12:00:00');
    const r = weekRange(wed);
    expect(r.from.getDay()).toBe(1);  // lunes
    expect(r.to.getDay()).toBe(0);    // domingo
    expect(r.label).toContain('2026');
    expect(r.label).toContain('–');
  });

  it('groupPostsByDay agrupa por YYYY-MM-DD y ordena por hora', () => {
    const posts = [
      { id: 'a', scheduled_at: '2026-05-19T15:00:00' },
      { id: 'b', scheduled_at: '2026-05-19T10:00:00' },
      { id: 'c', scheduled_at: '2026-05-20T08:00:00' },
    ];
    const out = groupPostsByDay(posts);
    expect(out['2026-05-19'].map((p) => p.id)).toEqual(['b', 'a']);
    expect(out['2026-05-20'].map((p) => p.id)).toEqual(['c']);
  });

  it('personaColorMap asigna color único por id (rotación)', () => {
    const personas = [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }];
    const m = personaColorMap(personas);
    expect(m.p1).toBeTruthy();
    expect(m.p2).toBeTruthy();
    expect(m.p3).toBeTruthy();
    expect(m.p1).not.toBe(m.p2);
  });

  it('formatTimeSlot formato HH:MM', () => {
    expect(formatTimeSlot('2026-05-19T11:05:00')).toMatch(/11:05/);
    expect(formatTimeSlot('not a date')).toBe('—');
  });

  it('canApprove lee el capability del permissions', () => {
    expect(canApprove({ can: (cap) => cap === 'influencer.posts.approve_publish' })).toBe(true);
    expect(canApprove({ can: () => false })).toBe(false);
    expect(canApprove(null)).toBe(false);
  });

  it('buildSchedulePayload aplica defaults', () => {
    const out = buildSchedulePayload({
      persona_id: 'p1', kind: 'photo', platforms: ['ig'], caption: 'hola',
    });
    expect(out.persona_id).toBe('p1');
    expect(out.kind).toBe('photo');
    expect(out.mode).toBe('scheduled');
  });
});
