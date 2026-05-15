import { describe, it, expect } from 'vitest';

import {
  consentStatusLabel,
  contactDisplayName,
  contactInitials,
  notesCount,
  summaryStats,
} from './contactProfileData.js';

describe('contactProfileData', () => {
  it('contactDisplayName falls back through name → phone → wa_id → default', () => {
    expect(contactDisplayName({ display_name: 'Laura Martínez' })).toBe('Laura Martínez');
    expect(contactDisplayName({ phone_e164: '+573000008842' })).toBe('+573000008842');
    expect(contactDisplayName({ wa_id: 'wa-1' })).toBe('wa-1');
    expect(contactDisplayName(null)).toBe('Contacto');
  });

  it('contactInitials derives two-letter initials and handles single words', () => {
    expect(contactInitials({ display_name: 'Laura Martínez' })).toBe('LM');
    expect(contactInitials({ display_name: 'Laura' })).toBe('LA');
    expect(contactInitials({ phone_e164: '+573000008842' })).toBe('+5');
    expect(contactInitials(null)).toBe('CO');
  });

  it('summaryStats derives the headline KPIs from the stats block', () => {
    const stats = summaryStats({
      total_appointments: 8,
      completed_appointments: 6,
      average_rating: 4.5,
      ratings_count: 4,
    });
    expect(stats).toHaveLength(3);
    expect(stats[0]).toEqual({ key: 'total', label: 'Citas totales', value: '8' });
    expect(stats[1].value).toBe('6');
    expect(stats[2].value).toBe('4.50 ★ (4)');
  });

  it('summaryStats tolerates a missing stats block', () => {
    const stats = summaryStats(null);
    expect(stats[0].value).toBe('0');
    expect(stats[2].value).toBe('—');
  });

  it('notesCount and consentStatusLabel read the profile/consent payloads', () => {
    expect(notesCount({ notes: [{ id: 1 }, { id: 2 }] })).toBe(2);
    expect(notesCount({})).toBe(0);
    expect(
      consentStatusLabel({ contact: { opt_in_status: 'unknown' } }, { contact: { opt_in_status: 'opted_in' } }),
    ).toBe('opted_in');
    expect(consentStatusLabel({ contact: { opt_in_status: 'opted_out' } }, null)).toBe('opted_out');
    expect(consentStatusLabel({}, null)).toBe('—');
  });
});
