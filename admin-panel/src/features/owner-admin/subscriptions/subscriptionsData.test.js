import { describe, it, expect } from 'vitest';

import {
  billingPeriodLabel,
  buildPlanPayload,
  computeKpis,
  emptyPlanForm,
  filterSubscribers,
  monthlyAmount,
  subscriptionStatusLabel,
  toPlanForm,
} from './subscriptionsData.js';

describe('subscriptionsData', () => {
  it('emptyPlanForm starts blank with sane defaults', () => {
    const form = emptyPlanForm();
    expect(form.id).toBeNull();
    expect(form.name).toBe('');
    expect(form.billing_period).toBe('monthly');
    expect(form.currency).toBe('COP');
    expect(form.status).toBe('active');
  });

  it('toPlanForm maps a plan record into the edit-form shape', () => {
    const form = toPlanForm({
      id: 'plan-1',
      name: 'Membresía VIP',
      billing_period: 'quarterly',
      price_amount: 720000,
      currency: 'cop',
      status: 'archived',
    });
    expect(form.id).toBe('plan-1');
    expect(form.billing_period).toBe('quarterly');
    expect(form.price_amount).toBe(720000);
    expect(form.status).toBe('archived');
  });

  it('buildPlanPayload rejects an empty name or a negative price', () => {
    expect(buildPlanPayload({ ...emptyPlanForm(), name: '   ' }).error).toMatch(/nombre/i);
    expect(buildPlanPayload({ ...emptyPlanForm(), name: 'X', price_amount: -5 }).error).toMatch(
      /precio/i,
    );
  });

  it('buildPlanPayload normalises a valid form', () => {
    const { payload, error } = buildPlanPayload({
      id: 'plan-1',
      name: '  Anual premium  ',
      description: '   ',
      billing_period: 'yearly',
      price_amount: '2400000',
      currency: 'usd',
      status: 'active',
    });
    expect(error).toBeUndefined();
    expect(payload).toEqual({
      name: 'Anual premium',
      description: null,
      billing_period: 'yearly',
      price_amount: 2400000,
      currency: 'USD',
      status: 'active',
    });
  });

  it('monthlyAmount normalises quarterly and yearly prices to a month', () => {
    expect(monthlyAmount({ billing_period: 'monthly', price_amount: 280000 })).toBe(280000);
    expect(monthlyAmount({ billing_period: 'quarterly', price_amount: 720000 })).toBe(240000);
    expect(monthlyAmount({ billing_period: 'yearly', price_amount: 2400000 })).toBe(200000);
  });

  it('computeKpis derives MRR and the subscriber counts from the lists', () => {
    const plans = [
      { id: 'p1', name: 'VIP', billing_period: 'monthly', price_amount: 280000, currency: 'COP', status: 'active' },
      { id: 'p2', name: 'Anual', billing_period: 'yearly', price_amount: 2400000, currency: 'COP', status: 'archived' },
    ];
    const subscribers = [
      { id: 's1', status: 'active', plan_id: 'p1' },
      { id: 's2', status: 'active', plan_id: 'p2' },
      { id: 's3', status: 'past_due', plan_id: 'p1' },
      { id: 's4', status: 'cancelled', plan_id: 'p1' },
    ];
    const kpis = computeKpis(plans, subscribers);
    // 280000 (monthly) + 2400000/12 = 200000 → 480000
    expect(kpis.mrr).toBe(480000);
    expect(kpis.activeCount).toBe(2);
    expect(kpis.pastDueCount).toBe(1);
    expect(kpis.cancelledCount).toBe(1);
    expect(kpis.activePlanCount).toBe(1);
  });

  it('filterSubscribers narrows the list by the active tab', () => {
    const subscribers = [
      { id: 's1', status: 'active' },
      { id: 's2', status: 'past_due' },
      { id: 's3', status: 'cancelled' },
    ];
    expect(filterSubscribers(subscribers, 'all')).toHaveLength(3);
    expect(filterSubscribers(subscribers, 'past_due')).toEqual([{ id: 's2', status: 'past_due' }]);
  });

  it('labels billing periods and statuses in Spanish', () => {
    expect(billingPeriodLabel('monthly')).toBe('Mensual');
    expect(billingPeriodLabel('yearly')).toBe('Anual');
    expect(subscriptionStatusLabel('past_due')).toBe('Cobro fallido');
    expect(subscriptionStatusLabel('active')).toBe('Activo');
  });
});
