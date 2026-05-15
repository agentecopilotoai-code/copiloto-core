import { describe, it, expect } from 'vitest';

import {
  DEFAULT_PRESET,
  RANGE_PRESETS,
  buildAgentKpis,
  buildAgentsCsv,
  buildLoadDistribution,
  rangeFromPreset,
} from './agentPerformanceData.js';

const SAMPLE = {
  totals: {
    agents: 4,
    messages_sent: 7712,
    handoffs_resolved: 356,
    handoffs_accepted: 360,
    revenue_attributed: 31840,
    appointments_confirmed: 276,
  },
  top_performer_user_id: 'agent-diana',
  items: [
    {
      user_id: 'agent-diana',
      display_name: 'Diana Pérez',
      email: 'diana@acme.co',
      messages_sent: 1640,
      handoffs_resolved: 192,
      handoffs_accepted: 192,
      appointments_confirmed: 152,
      revenue_attributed: 17120,
      avg_response_time_seconds: 42,
      feedback_avg_rating: 4.9,
      feedback_ratings_count: 30,
    },
    {
      user_id: 'agent-luis',
      display_name: 'Luis Rivas',
      email: 'luis@acme.co',
      messages_sent: 1552,
      handoffs_resolved: 164,
      handoffs_accepted: 168,
      appointments_confirmed: 124,
      revenue_attributed: 14720,
      avg_response_time_seconds: 51,
      feedback_avg_rating: 4.8,
      feedback_ratings_count: 24,
    },
    {
      user_id: 'agent-paola',
      display_name: 'Paola Núñez',
      email: 'paola@acme.co',
      messages_sent: 2496,
      handoffs_resolved: 0,
      handoffs_accepted: 0,
      appointments_confirmed: 0,
      revenue_attributed: 0,
      avg_response_time_seconds: 28,
      feedback_avg_rating: 4.7,
      feedback_ratings_count: 18,
    },
  ],
};

describe('agentPerformanceData', () => {
  describe('rangeFromPreset', () => {
    it('exposes a default preset of 30d', () => {
      expect(DEFAULT_PRESET).toBe('30d');
      expect(RANGE_PRESETS.find((p) => p.id === DEFAULT_PRESET)).toBeDefined();
    });

    it('builds an inclusive ISO range that ends today', () => {
      const range = rangeFromPreset('7d');
      expect(range.fromDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(range.toDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      const from = new Date(range.fromDate);
      const to = new Date(range.toDate);
      const days = Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      expect(days).toBe(7);
    });

    it('falls back to 30d when an unknown preset is requested', () => {
      const range = rangeFromPreset('does-not-exist');
      const from = new Date(range.fromDate);
      const to = new Date(range.toDate);
      const days = Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      expect(days).toBe(30);
    });
  });

  describe('buildAgentKpis', () => {
    it('returns the 4 canonical KPIs from the HTML mockup', () => {
      const kpis = buildAgentKpis(SAMPLE);
      expect(kpis).toHaveLength(4);
      expect(kpis.map((k) => k.label)).toEqual([
        'Mensajes humanos · mes',
        'Handoffs cerrados',
        'Ingreso atribuido equipo',
        '1ª respuesta media',
      ]);
    });

    it('formats messages_sent with es-CO separators', () => {
      const kpis = buildAgentKpis(SAMPLE);
      expect(kpis[0].value).toBe('7.712');
    });

    it('formats revenue_attributed as COP currency', () => {
      const kpis = buildAgentKpis(SAMPLE);
      expect(kpis[2].value).toContain('31');
      expect(kpis[2].value).toContain('840');
    });

    it('computes the average first-response time over agents with samples', () => {
      const kpis = buildAgentKpis(SAMPLE);
      // (42 + 51 + 28) / 3 ≈ 40.3
      expect(kpis[3].value).toMatch(/40|41/);
    });

    it('falls back to em-dash and explanatory footnotes when totals are empty', () => {
      const kpis = buildAgentKpis({ totals: {}, items: [] });
      expect(kpis[0].value).toBe('0');
      expect(kpis[3].value).toBe('-');
      expect(kpis[3].footnote).toMatch(/Sin muestras/);
    });
  });

  describe('buildLoadDistribution', () => {
    it('produces one bar per agent sorted descending by messages_sent', () => {
      const series = buildLoadDistribution(SAMPLE);
      expect(series).toHaveLength(3);
      expect(series[0].label).toBe('Paola Núñez');
      expect(series[0].value).toBe(2496);
      expect(series[0].percent).toBe(100);
      expect(series[2].label).toBe('Luis Rivas');
    });

    it('returns an empty array when there are no agents', () => {
      expect(buildLoadDistribution(null)).toEqual([]);
      expect(buildLoadDistribution({ items: [] })).toEqual([]);
    });
  });

  describe('buildAgentsCsv', () => {
    it('emits a header line and one row per agent', () => {
      const csv = buildAgentsCsv(SAMPLE, {
        tenantId: 'tenant-acme',
        fromDate: '2026-04-15',
        toDate: '2026-05-15',
      });
      const lines = csv.split('\n');
      // 3 meta + 1 header + 3 agents = 7
      expect(lines).toHaveLength(7);
      expect(lines[0]).toContain('tenant_id=tenant-acme');
      expect(lines[3]).toBe(
        'persona,mensajes,handoffs_resueltos,handoffs_aceptados,citas_confirmadas,ingreso_atribuido,primer_respuesta_seg,rating,rating_count',
      );
      expect(lines[4]).toContain('"Diana Pérez"');
      expect(lines[4]).toContain('1640');
      expect(lines[4]).toContain('17120');
      expect(lines[4]).toContain('4.90');
    });

    it('escapes double quotes in display names', () => {
      const csv = buildAgentsCsv(
        { items: [{ user_id: 'x', display_name: 'Diana "DP" Pérez' }] },
        { tenantId: 't' },
      );
      expect(csv).toContain('"Diana ""DP"" Pérez"');
    });
  });
});
