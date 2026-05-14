import { describe, it, expect } from 'vitest';

import { buildAlerts, buildKpis, formatMoney } from './dashboardData.js';

const HEALTHY_OVERVIEW = {
  appointments: {
    created: 20,
    confirmed: 14,
    completed: 12,
    no_shows: 1,
    no_show_rate_pct: 7.4,
  },
  conversations: { open: 5, handoff: 0 },
  messages: { inbound: 320, outbound: 410 },
  revenue: { estimated_amount: 1840000 },
  feedback: { average_rating: 4.6, ratings_count: 18 },
};

const PREVIOUS_OVERVIEW = {
  appointments: { confirmed: 10, no_show_rate_pct: 9.0 },
  conversations: { open: 8 },
  messages: { inbound: 280 },
  revenue: { estimated_amount: 1500000 },
};

describe('dashboardData', () => {
  it('formatMoney renders a whole-number currency string', () => {
    expect(formatMoney(1840000)).toMatch(/1\.840\.000/);
    expect(formatMoney(0)).toMatch(/0/);
    expect(formatMoney(undefined)).toMatch(/0/);
  });

  it('buildKpis shapes the five KPI cards with current/previous values', () => {
    const kpis = buildKpis(HEALTHY_OVERVIEW, PREVIOUS_OVERVIEW);
    expect(kpis.map((k) => k.key)).toEqual([
      'appointments_confirmed',
      'no_show_rate',
      'conversations_open',
      'messages_inbound',
      'revenue',
    ]);
    const confirmed = kpis[0];
    expect(confirmed.current).toBe(14);
    expect(confirmed.previous).toBe(10);
    expect(confirmed.value).toBe('14');
    // no-show rate is a "lower is better" metric.
    expect(kpis[1].invertTrend).toBe(true);
  });

  it('buildKpis tolerates missing / null overview data', () => {
    const kpis = buildKpis(null, null);
    expect(kpis).toHaveLength(5);
    expect(kpis[0].current).toBe(0);
    expect(kpis[0].value).toBe('0');
  });

  it('buildAlerts returns no alerts for a healthy overview', () => {
    expect(buildAlerts(HEALTHY_OVERVIEW)).toEqual([]);
  });

  it('buildAlerts flags pending handoffs, low feedback and high no-show', () => {
    const alerts = buildAlerts({
      appointments: { no_show_rate_pct: 14.2 },
      conversations: { open: 9, handoff: 3 },
      feedback: { average_rating: 2.8, ratings_count: 11 },
    });
    const ids = alerts.map((a) => a.id);
    expect(ids).toEqual(['handoffs', 'feedback', 'no_show']);
    // a rating below 3 escalates the feedback alert to danger.
    expect(alerts.find((a) => a.id === 'feedback').tone).toBe('danger');
    expect(alerts.find((a) => a.id === 'handoffs').linkModule).toBe('operations-desk');
  });
});
