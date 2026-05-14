import { describe, it, expect } from 'vitest';

import {
  DEFAULT_BOT_PERSONALITY,
  DEFAULT_NOTIFICATION_SETTINGS,
} from './tenantSetupData.js';
import {
  hydrateBotPersonality,
  renderPersonalityPreview,
  hydrateNotificationSettings,
  hydrateIntentSettings,
  toBusinessHours,
  toEscalationPolicy,
  toPiiPolicy,
  slugifyVertical,
} from './tenantSetupTransforms.js';

describe('hydrateBotPersonality', () => {
  it('returns defaults for invalid input', () => {
    expect(hydrateBotPersonality(null)).toEqual(DEFAULT_BOT_PERSONALITY);
    expect(hydrateBotPersonality('not-json')).toEqual(DEFAULT_BOT_PERSONALITY);
  });

  it('merges valid values and clamps unknown enums + custom_persona length', () => {
    const merged = hydrateBotPersonality({
      tone: 'unknown',
      formality: 'vos',
      emoji_level: 'high',
      custom_persona: 'x'.repeat(700),
    });
    expect(merged.tone).toBe('neutral');
    expect(merged.formality).toBe('vos');
    expect(merged.emoji_level).toBe('high');
    expect(merged.custom_persona).toHaveLength(600);
  });
});

describe('renderPersonalityPreview', () => {
  it('substitutes business name and applies emoji suffix', () => {
    const sample = { id: 'greeting', title: 'x', base: '¡Hola! Soy el asistente de {business_name}.' };
    const out = renderPersonalityPreview(sample, { ...DEFAULT_BOT_PERSONALITY, emoji_level: 'moderate' }, 'Spa Demo');
    expect(out).toContain('Spa Demo');
    expect(out).toContain('👋');
  });
});

describe('hydrateNotificationSettings', () => {
  it('returns defaults for invalid input', () => {
    expect(hydrateNotificationSettings(null)).toEqual(DEFAULT_NOTIFICATION_SETTINGS);
  });

  it('normalizes complaint_alert_channels', () => {
    const out = hydrateNotificationSettings({
      complaint_alert_channels: { email: [' a@b.com ', 1], whatsapp: null, webhook_url: ' https://x ' },
    });
    expect(out.complaint_alert_channels).toEqual({
      email: ['a@b.com'],
      whatsapp: [],
      webhook_url: 'https://x',
    });
  });
});

describe('hydrateIntentSettings', () => {
  it('fills gaps with defaults and respects saved keywords', () => {
    const out = hydrateIntentSettings({ custom_keywords: { greeting: ['ey'] }, min_confidence: 0.8 });
    expect(out.custom_keywords.greeting).toEqual(['ey']);
    expect(out.custom_keywords.faq.length).toBeGreaterThan(0);
    expect(out.min_confidence).toBe(0.8);
  });
});

describe('toBusinessHours', () => {
  it('builds weekly_schedule with enabled days only', () => {
    const hoursForm = {
      mon: { enabled: true, start: '09:00', end: '18:00' },
      tue: { enabled: false, start: '09:00', end: '18:00' },
      wed: { enabled: false, start: '09:00', end: '18:00' },
      thu: { enabled: false, start: '09:00', end: '18:00' },
      fri: { enabled: false, start: '09:00', end: '18:00' },
      sat: { enabled: false, start: '09:00', end: '18:00' },
      sun: { enabled: false, start: '09:00', end: '18:00' },
    };
    const out = toBusinessHours(hoursForm);
    expect(out.timezone_strategy).toBe('tenant_timezone');
    expect(out.weekly_schedule.mon).toEqual([{ start: '09:00', end: '18:00' }]);
    expect(out.weekly_schedule.tue).toEqual([]);
  });
});

describe('toEscalationPolicy', () => {
  it('coerces numeric fields and splits keywords', () => {
    const out = toEscalationPolicy({
      enabled: true,
      queue: 'q',
      priority: 'high',
      afterBotTurns: '7',
      confidenceBelow: '0.4',
      keywords: 'humano, asesor ,',
      handoffMessage: 'msg',
      consecutiveNoContextLimit: '3',
      enforceServiceWindow: false,
      selfServiceMinHoursBeforeStart: '2',
    });
    expect(out.triggers.after_bot_turns).toBe(7);
    expect(out.triggers.confidence_below).toBe(0.4);
    expect(out.triggers.keywords).toEqual(['humano', 'asesor']);
    expect(out.self_service.min_hours_before_start).toBe(2);
  });
});

describe('toPiiPolicy', () => {
  it('coerces retention_days to a number', () => {
    const out = toPiiPolicy({
      mode: 'strict',
      retentionDays: '90',
      redactBeforeModel: true,
      logRedaction: false,
      rules: { phone: 'mask' },
    });
    expect(out.retention_days).toBe(90);
    expect(out.mode).toBe('strict');
    expect(out.rules).toEqual({ phone: 'mask' });
  });
});

describe('slugifyVertical', () => {
  it('normalizes accents and non-alphanumerics to snake_case', () => {
    expect(slugifyVertical('Clínica Dental')).toBe('clinica_dental');
    expect(slugifyVertical('  Taller!! Mecánico  ')).toBe('taller_mecanico');
    expect(slugifyVertical('')).toBe('');
  });
});
