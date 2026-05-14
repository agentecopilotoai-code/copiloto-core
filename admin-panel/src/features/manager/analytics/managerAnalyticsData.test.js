import { describe, it, expect } from 'vitest';
import {
  buildCampaignRows,
  buildFunnelSegments,
  buildManagerKpis,
  channelLabel,
  formatCurrency,
  formatSeconds,
  sortAgents,
} from './managerAnalyticsData.js';

describe('managerAnalyticsData', () => {
  it('formats currency and falls back to "-" for empty values', () => {
    expect(formatCurrency(null)).toBe('-');
    expect(formatCurrency(undefined)).toBe('-');
    expect(formatCurrency(26400)).toMatch(/26\.400/);
  });

  it('formats durations in s / min / h', () => {
    expect(formatSeconds(0)).toBe('-');
    expect(formatSeconds(42)).toBe('42 s');
    expect(formatSeconds(90)).toBe('1.5 min');
    expect(formatSeconds(7200)).toBe('2.0 h');
  });

  it('sorts agents descending by metric, ascending by response time', () => {
    const agents = [
      { user_id: 'a', revenue_attributed: 100, avg_response_time_seconds: 60 },
      { user_id: 'b', revenue_attributed: 300, avg_response_time_seconds: 20 },
      { user_id: 'c', revenue_attributed: 200, avg_response_time_seconds: 0 },
    ];
    expect(sortAgents(agents, 'revenue_attributed').map((a) => a.user_id)).toEqual([
      'b',
      'c',
      'a',
    ]);
    // response time: 0 / falsy is treated as "infinite" (no data → last)
    expect(sortAgents(agents, 'avg_response_time_seconds').map((a) => a.user_id)).toEqual([
      'b',
      'a',
      'c',
    ]);
  });

  it('builds KPI descriptors from real overview fields only', () => {
    const current = {
      revenue: { estimated_amount: 26400 },
      appointments: { completed: 312, confirmed: 340, no_show_rate_pct: 8 },
      retention: { retention_rate_pct: 41, recurring_contacts: 120 },
      conversations: { handoff: 5 },
    };
    const previous = {
      revenue: { estimated_amount: 22000 },
      appointments: { completed: 290, no_show_rate_pct: 11 },
      retention: { retention_rate_pct: 38 },
    };
    const kpis = buildManagerKpis(current, previous);
    expect(kpis.map((k) => k.key)).toEqual([
      'revenue',
      'appointments_completed',
      'retention',
      'no_show_rate',
    ]);
    expect(kpis[1].current).toBe(312);
    expect(kpis[1].previous).toBe(290);
    expect(kpis[3].invertTrend).toBe(true);
  });

  it('derives funnel segments with channel labels and percentages', () => {
    const funnel = {
      by_channel: [
        {
          channel: 'whatsapp',
          steps: [{ step: 'appointments_scheduled', count: 174 }],
        },
        {
          channel: 'instagram',
          steps: [{ step: 'appointments_scheduled', count: 26 }],
        },
      ],
    };
    const segments = buildFunnelSegments(funnel);
    expect(segments[0]).toMatchObject({ label: 'WhatsApp', count: 174 });
    expect(Math.round(segments[0].percent)).toBe(87);
    expect(segments[1].label).toBe('Instagram');
    expect(buildFunnelSegments(null)).toEqual([]);
  });

  it('builds campaign rows and resolves channel labels', () => {
    const campaigns = {
      items: [
        {
          campaign_id: 'c1',
          name: 'Promo Día de la Madre',
          status: 'sent',
          recipients: 1240,
          appointments_attributed: 142,
          revenue_attributed: 12480,
        },
      ],
    };
    const rows = buildCampaignRows(campaigns);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: 'c1', recipients: 1240, revenue: 12480 });
    expect(buildCampaignRows(null)).toEqual([]);
    expect(channelLabel('web_widget')).toBe('Web widget');
    expect(channelLabel('telegram')).toBe('telegram');
  });
});
