import { describe, expect, it } from 'vitest';

import {
  SUMMARY_DESCRIPTION,
  buildKpis,
  formatMoney,
  periodLabel,
} from './summaryData.js';

describe('summaryData', () => {
  describe('periodLabel', () => {
    it('renders "Últimos 7 días · <mes> <año>" en español', () => {
      const may2026 = new Date(2026, 4, 14); // mes 4 = mayo (0-indexed)
      expect(periodLabel(may2026)).toBe('Últimos 7 días · Mayo 2026');
    });

    it('cubre todos los meses (sin huecos en la tabla de nombres)', () => {
      const enero = new Date(2026, 0, 1);
      const diciembre = new Date(2026, 11, 31);
      expect(periodLabel(enero)).toBe('Últimos 7 días · Enero 2026');
      expect(periodLabel(diciembre)).toBe('Últimos 7 días · Diciembre 2026');
    });

    it('cae a la fecha actual si no se le pasa argumento', () => {
      const label = periodLabel();
      expect(label).toMatch(/^Últimos 7 días · [A-ZÁÉÍÓÚ][a-záéíóú]+ \d{4}$/);
    });
  });

  describe('SUMMARY_DESCRIPTION', () => {
    it('menciona el período semanal y la cadencia de refresh de 15 minutos', () => {
      expect(SUMMARY_DESCRIPTION).toMatch(/última semana/i);
      expect(SUMMARY_DESCRIPTION).toMatch(/15 minutos/i);
    });
  });

  describe('re-exports del dashboard', () => {
    // El backlog manda "Versión read-only de UI-007.1. Reusa KpiCardWithDelta".
    // Estos re-exports garantizan que la vista Viewer consume EXACTAMENTE las
    // mismas helpers del Owner/Admin dashboard — si alguien las renombra/borra
    // sin actualizar el barrel, estos tests se rompen ruidosamente.
    it('reexporta buildKpis del dashboard', () => {
      expect(typeof buildKpis).toBe('function');
      const kpis = buildKpis(null, null);
      expect(Array.isArray(kpis)).toBe(true);
      expect(kpis.length).toBeGreaterThan(0);
    });

    it('reexporta formatMoney del dashboard', () => {
      expect(typeof formatMoney).toBe('function');
      // No verificamos un literal exacto (Intl es env-dependent) — solo que
      // devuelve un string no vacío para un número finito.
      expect(formatMoney(12345)).toMatch(/12/);
    });
  });
});
