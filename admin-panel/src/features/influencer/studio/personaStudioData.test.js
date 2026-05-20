import { describe, it, expect } from 'vitest';

import {
  formatScheduledCount,
  nextPostLabel,
  statusLabel,
  tagsFromVoice,
} from './personaStudioData.js';


describe('personaStudioData', () => {
  it('statusLabel mapea estados a español', () => {
    expect(statusLabel('active')).toBe('Activo');
    expect(statusLabel('paused')).toBe('Pausado');
    expect(statusLabel('draft')).toBe('Borrador');
    expect(statusLabel('archived')).toBe('Archivado');
    expect(statusLabel(null)).toBe('Sin estado');
  });

  it('formatScheduledCount construye "ACTIVO · N PROGRAMADOS"', () => {
    expect(formatScheduledCount('active', 12)).toBe('ACTIVO · 12 PROGRAMADOS');
    expect(formatScheduledCount('active', 1)).toBe('ACTIVO · 1 PROGRAMADO');
    expect(formatScheduledCount('active', 0)).toBe('ACTIVO');
    expect(formatScheduledCount('paused', 5)).toBe('PAUSADO · 5 PROGRAMADOS');
  });

  it('nextPostLabel produce labels relativos (hoy/mañana/fecha)', () => {
    const baseNow = new Date('2026-05-19T09:00:00');
    // Hoy
    expect(nextPostLabel(
      { at: '2026-05-19T11:00:00', platforms: ['ig', 'yt'] }, baseNow,
    )).toBe('11:00 hoy · IG, YT');
    // Mañana
    expect(nextPostLabel(
      { at: '2026-05-20T18:30:00', platforms: ['tiktok'] }, baseNow,
    )).toBe('18:30 mañana · TIKTOK');
    // Más tarde — formato dd MMM
    const later = nextPostLabel(
      { at: '2026-06-10T09:15:00', platforms: ['ig'] }, baseNow,
    );
    expect(later).toMatch(/^09:15 \d{2}/);  // "09:15 10 jun"
    expect(later).toContain('IG');
    // Sin next_post
    expect(nextPostLabel(null, baseNow)).toBeNull();
    expect(nextPostLabel({ at: 'not-a-date', platforms: [] }, baseNow)).toBeNull();
  });

  it('tagsFromVoice extrae tone+formality+style_tokens, omite neutral', () => {
    expect(tagsFromVoice({
      tone: 'cálida',
      formality: 'informal',
      style_tokens: ['resort wear', 'joyería'],
    })).toEqual(['Cálida', 'Informal', 'Resort wear', 'Joyería']);

    expect(tagsFromVoice({
      tone: 'cercana',
      formality: 'neutral',  // omitido
      style_tokens: ['hospitality'],
    })).toEqual(['Cercana', 'Hospitality']);

    expect(tagsFromVoice({})).toEqual([]);
  });
});
