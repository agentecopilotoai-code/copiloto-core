import { describe, expect, it } from 'vitest';

import {
  ACCOUNT_LOCALES,
  ACCOUNT_TIMEZONES,
  DEFAULT_SESSIONS,
  NOTIFICATION_CHANNELS,
  NOTIFICATION_EVENTS,
  THEME_OPTIONS,
  deriveProfileForm,
  initialNotificationMatrix,
  profileDisplayName,
  profileInitials,
  profileRoleLabel,
  toggleNotificationChannel,
} from './accountData.js';

describe('accountData — catálogos estáticos', () => {
  it('expone ≥ 1 locale y zona horaria con shape { value, label }', () => {
    expect(ACCOUNT_LOCALES.length).toBeGreaterThan(0);
    for (const option of ACCOUNT_LOCALES) {
      expect(option).toMatchObject({ value: expect.any(String), label: expect.any(String) });
    }
    expect(ACCOUNT_TIMEZONES.length).toBeGreaterThan(0);
    expect(ACCOUNT_TIMEZONES[0]).toMatchObject({ value: 'America/Bogota' });
  });

  it('expone los 3 canales y los 6 eventos del HTML T3', () => {
    expect(NOTIFICATION_CHANNELS.map((c) => c.id)).toEqual(['email', 'wa', 'inapp']);
    expect(NOTIFICATION_EVENTS.length).toBe(6);
    expect(NOTIFICATION_EVENTS.map((e) => e.id)).toContain('daily_digest');
    expect(NOTIFICATION_EVENTS.map((e) => e.id)).toContain('quality_rating_low');
    expect(NOTIFICATION_EVENTS.map((e) => e.id)).toContain('weekly_campaigns_summary');
  });

  it('THEME_OPTIONS lista auto / light / dark en ese orden', () => {
    expect(THEME_OPTIONS.map((o) => o.value)).toEqual(['auto', 'light', 'dark']);
  });

  it('DEFAULT_SESSIONS marca exactamente una sesión como current', () => {
    const current = DEFAULT_SESSIONS.filter((s) => s.current);
    expect(current).toHaveLength(1);
    expect(current[0].device).toMatch(/Chrome|macOS/);
  });
});

describe('accountData — derivación de profile', () => {
  it('deriveProfileForm usa email split como fallback si falta name', () => {
    const form = deriveProfileForm({ email: 'camila@clinicaen.co' });
    expect(form.name).toBe('camila');
    expect(form.email).toBe('camila@clinicaen.co');
    expect(form.locale).toBe('es-CO');
    expect(form.timezone).toBe('America/Bogota');
  });

  it('deriveProfileForm respeta name y phone si vienen del profile', () => {
    const form = deriveProfileForm({
      name: 'Camila Rojas Martínez',
      email: 'camila@clinicaen.co',
      phone_number: '+57 300 8842 100',
    });
    expect(form.name).toBe('Camila Rojas Martínez');
    expect(form.phone).toBe('+57 300 8842 100');
  });

  it('profileInitials usa primeras letras de las dos palabras del nombre', () => {
    expect(profileInitials({ name: 'Camila Rojas' })).toBe('CR');
    expect(profileInitials({ name: 'Camila' })).toBe('CA');
    expect(profileInitials({ email: 'lucas@x.co' })).toBe('LU');
    expect(profileInitials(null)).toBe('U');
  });

  it('profileDisplayName / profileRoleLabel devuelven defaults legibles', () => {
    expect(profileDisplayName({ name: 'Camila' })).toBe('Camila');
    expect(profileDisplayName(null)).toBe('Usuario');
    expect(profileRoleLabel({ roles: ['owner'] })).toBe('owner');
    expect(profileRoleLabel({})).toBe('sin rol');
  });
});

describe('accountData — matriz de notificaciones', () => {
  it('initialNotificationMatrix pinta los defaults del catálogo', () => {
    const matrix = initialNotificationMatrix();
    expect(matrix.daily_digest).toMatchObject({ email: true, wa: true, inapp: false });
    expect(matrix.payment_failed).toMatchObject({ email: true, inapp: false });
    expect(Object.keys(matrix)).toHaveLength(NOTIFICATION_EVENTS.length);
  });

  it('toggleNotificationChannel produce una copia inmutable e invierte el flag', () => {
    const before = initialNotificationMatrix();
    const after = toggleNotificationChannel(before, 'daily_digest', 'email');
    expect(after).not.toBe(before);
    expect(after.daily_digest.email).toBe(false);
    // Otras filas intactas.
    expect(after.payment_failed).toEqual(before.payment_failed);
  });

  it('toggleNotificationChannel maneja eventos sin entry previa', () => {
    const empty = {};
    const next = toggleNotificationChannel(empty, 'daily_digest', 'inapp');
    expect(next.daily_digest.inapp).toBe(true);
  });
});
