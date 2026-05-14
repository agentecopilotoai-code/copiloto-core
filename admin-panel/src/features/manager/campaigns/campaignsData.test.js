import { describe, it, expect } from 'vitest';

import {
  buildDeliveryMetrics,
  buildPayload,
  deliveryPercent,
  emptyCampaignForm,
  formFromCampaign,
  parseVariables,
  serializeVariables,
  statusLabel,
  statusTone,
} from './campaignsData.js';

describe('campaignsData', () => {
  it('maps campaign status to Spanish labels and badge tones', () => {
    expect(statusLabel('draft')).toBe('Borrador');
    expect(statusLabel('running')).toBe('En curso');
    expect(statusLabel('unknown')).toBe('unknown');
    expect(statusTone('completed')).toBe('success');
    expect(statusTone('cancelled')).toBe('danger');
    expect(statusTone('weird')).toBe('neutral');
  });

  it('parses and serializes a clave=valor variables block round-trip', () => {
    const parsed = parseVariables('2=Promo\n1=María\n\nbad line\n10=Junio');
    expect(parsed).toEqual({ 2: 'Promo', 1: 'María', 10: 'Junio' });
    // serialize orders numeric keys numerically (1, 2, 10).
    expect(serializeVariables(parsed)).toBe('1=María\n2=Promo\n10=Junio');
    expect(serializeVariables(null)).toBe('');
  });

  it('builds the payload from a valid form', () => {
    const form = {
      ...emptyCampaignForm(),
      name: '  Promo octubre  ',
      template_id: 'tpl-1',
      template_variables: '1=María',
      segment_id: '',
      segment: { ...emptyCampaignForm().segment, min_appointments: '3' },
    };
    const { payload, error } = buildPayload(form);
    expect(error).toBeUndefined();
    expect(payload.name).toBe('Promo octubre');
    expect(payload.template_id).toBe('tpl-1');
    expect(payload.template_variables).toEqual({ 1: 'María' });
    expect(payload.segment_filter).toEqual({ min_appointments: 3 });
    expect(payload.segment_id).toBeNull();
  });

  it('rejects a payload missing name or template, and prefers segment_id over filters', () => {
    expect(buildPayload({ ...emptyCampaignForm(), name: '', template_id: 'x' }).error).toMatch(
      /obligatorios/i,
    );
    const withSegment = buildPayload({
      ...emptyCampaignForm(),
      name: 'Campaña',
      template_id: 'tpl-1',
      segment_id: 'seg-9',
      segment: { ...emptyCampaignForm().segment, min_appointments: '5' },
    });
    expect(withSegment.payload.segment_id).toBe('seg-9');
    // when a saved segment is picked, segment_filter is emptied.
    expect(withSegment.payload.segment_filter).toEqual({});
  });

  it('hydrates the form from a campaign record', () => {
    const form = formFromCampaign({
      name: 'Reactivación',
      template_id: 'tpl-7',
      template_variables: { 1: 'Hola' },
      scheduled_at: '2026-06-01T15:30:00Z',
      segment_id: 'seg-3',
      segment_filter: { tags: ['t1'], has_upcoming_appointment: false },
    });
    expect(form.name).toBe('Reactivación');
    expect(form.template_id).toBe('tpl-7');
    expect(form.template_variables).toBe('1=Hola');
    expect(form.segment_id).toBe('seg-3');
    expect(form.segment.tags).toEqual(['t1']);
    expect(form.segment.has_upcoming_appointment).toBe('no');
  });

  it('derives delivery metrics with clamped percentages', () => {
    expect(deliveryPercent(5, 10)).toBe(50);
    expect(deliveryPercent(3, 0)).toBe(0);
    expect(deliveryPercent(20, 10)).toBe(100);
    const metrics = buildDeliveryMetrics({
      recipient_count: 100,
      sent_count: 80,
      delivered_count: 70,
      read_count: 40,
      failed_count: 10,
    });
    expect(metrics.map((m) => m.key)).toEqual(['sent', 'delivered', 'read', 'failed']);
    expect(metrics[0]).toMatchObject({ value: 80, total: 100, percent: 80 });
    expect(metrics[3]).toMatchObject({ value: 10, percent: 10 });
    expect(buildDeliveryMetrics(null)).toEqual([]);
  });
});
