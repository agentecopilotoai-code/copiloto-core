import { useMemo } from 'react';

import { useDashboardData } from '../../../owner-admin/dashboard/index.js';
import { periodLabel } from '../summaryData.js';

/**
 * UI-010.1 — capa de datos de la vista «Resumen del negocio» (Viewer).
 *
 * Wrapper fino sobre `useDashboardData` (UI-007.1). NO refetchea nada: reusa
 * verbatim los dos llamados a `getAnalyticsOverview` (ventana actual + previa)
 * que el dashboard del Owner/Admin ya hace. Encima añade sólo:
 *   1. el `periodLabel` derivado de la fecha actual, para el chip de período,
 *   2. el flag `readOnly: true` para señalizar a los consumidores que esta
 *      vista no expone CTAs de escritura (UI-010 criterio global).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|undefined} options.tenantId — active tenant id
 * @returns {{
 *   current: object|null,
 *   previous: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   readOnly: true,
 *   periodLabel: string,
 * }}
 */
export function useSummaryData({ session, tenantId }) {
  const { current, previous, loading, error } = useDashboardData({ session, tenantId });
  // Memoize the period label so the chip text is stable across re-renders;
  // the underlying `new Date()` only changes when the component remounts.
  const label = useMemo(() => periodLabel(), []);

  return {
    current,
    previous,
    loading,
    error,
    readOnly: true,
    periodLabel: label,
  };
}
