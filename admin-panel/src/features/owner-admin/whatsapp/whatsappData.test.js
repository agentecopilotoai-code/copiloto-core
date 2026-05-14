import { describe, it, expect } from 'vitest';

import {
  buildChecklist,
  buildRequiredSemaphore,
  channelFromHealth,
  defaultFormForTenant,
  emptyTemplateForm,
  formFromChannel,
  groupTemplatesByPurpose,
  hasValue,
  templateComponentsFromForm,
  validateTemplateForm,
} from './whatsappData.js';

describe('whatsappData', () => {
  it('emptyTemplateForm and defaultFormForTenant start blank with sane defaults', () => {
    expect(emptyTemplateForm().locale).toBe('es');
    expect(emptyTemplateForm().purpose).toBe('appointment_confirmation');
    const channelForm = defaultFormForTenant();
    expect(channelForm.account_mode).toBe('mock');
    expect(channelForm.business_id).toBe('');
  });

  it('formFromChannel maps a channel record but never carries secrets', () => {
    const form = formFromChannel({
      business_id: 'b-1',
      waba_id: 'w-1',
      phone_number_id: 'p-1',
      account_mode: 'live',
    });
    expect(form.business_id).toBe('b-1');
    expect(form.account_mode).toBe('live');
    expect(form.meta_access_token).toBe('');
    expect(form.app_secret).toBe('');
    expect(form.verify_token).toBe('');
  });

  it('templateComponentsFromForm builds the Meta components object', () => {
    const components = templateComponentsFromForm({
      header: 'Recordatorio',
      body: 'Hola {{1}}',
      footer: '',
      buttons: 'Confirmar\n  \nReagendar',
    });
    expect(components.header).toEqual({ type: 'text', text: 'Recordatorio' });
    expect(components.body).toEqual({ text: 'Hola {{1}}' });
    expect(components.footer).toBeUndefined();
    expect(components.buttons).toEqual([
      { type: 'QUICK_REPLY', text: 'Confirmar' },
      { type: 'QUICK_REPLY', text: 'Reagendar' },
    ]);
  });

  it('validateTemplateForm enforces name + body and snake_case naming', () => {
    expect(validateTemplateForm({ name: '', body: 'x' })).toMatch(/obligatorios/i);
    expect(validateTemplateForm({ name: 'Bad Name', body: 'x' })).toMatch(/snake_case/i);
    expect(validateTemplateForm({ name: 'good_name', body: 'x' })).toBeNull();
  });

  it('hasValue and channelFromHealth read their inputs defensively', () => {
    expect(hasValue('  ')).toBe(false);
    expect(hasValue(' x ')).toBe(true);
    expect(channelFromHealth(null)).toBeNull();
    expect(channelFromHealth({ channel: { id: 'c-1' } })).toEqual({ id: 'c-1' });
  });

  it('groupTemplatesByPurpose buckets templates by their purpose', () => {
    const grouped = groupTemplatesByPurpose([
      { id: 't1', purpose: 'appointment_confirmation' },
      { id: 't2', purpose: 'appointment_confirmation' },
      { id: 't3', purpose: 'campaign_promo' },
    ]);
    expect(grouped.appointment_confirmation).toHaveLength(2);
    expect(grouped.campaign_promo).toHaveLength(1);
  });

  it('buildChecklist marks steps done from the form + health snapshot', () => {
    const steps = buildChecklist(
      {
        business_id: 'b-1',
        waba_id: 'w-1',
        phone_number_id: 'p-1',
        meta_access_token: 'tok',
        app_secret: 'sec',
        verify_token: 'ver',
      },
      { status: 'healthy', checks: {} },
      { status: 'active' },
    );
    const done = Object.fromEntries(steps.map((s) => [s.id, s.done]));
    expect(done).toEqual({
      business: true,
      waba: true,
      phone: true,
      secrets: true,
      health: true,
    });
  });

  it('buildRequiredSemaphore flags required purposes by approval state', () => {
    const semaphore = buildRequiredSemaphore({
      appointment_confirmation: [{ status: 'approved' }],
      appointment_reminder_24h: [{ status: 'pending' }],
    });
    const byId = Object.fromEntries(semaphore.map((s) => [s.id, s.tone]));
    expect(byId.appointment_confirmation).toBe('green');
    expect(byId.appointment_reminder_24h).toBe('yellow');
  });
});
