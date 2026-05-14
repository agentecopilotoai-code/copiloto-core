import { useCallback, useEffect, useState } from 'react';

import {
  getAnalyticsAgents,
  getAnalyticsCampaigns,
  getAnalyticsFunnel,
  getAnalyticsOverview,
} from '../../../../services/coreApi.js';

/** Presets de rango disponibles en la cabecera del panel. */
export const RANGE_PRESETS = Object.freeze([
  { id: '14d', label: '14 días', days: 14 },
  { id: '30d', label: '30 días', days: 30 },
  { id: '90d', label: '90 días', days: 90 },
]);

const DEFAULT_PRESET = '14d';

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

/** Ventana actual y previa (mismo tamaño) para deltas like-for-like. */
function buildRanges(days) {
  const today = new Date();
  const currentFrom = new Date(today);
  currentFrom.setDate(currentFrom.getDate() - (days - 1));
  const previousTo = new Date(today);
  previousTo.setDate(previousTo.getDate() - days);
  const previousFrom = new Date(today);
  previousFrom.setDate(previousFrom.getDate() - days * 2 + 1);
  return {
    current: { fromDate: isoDate(currentFrom), toDate: isoDate(today) },
    previous: { fromDate: isoDate(previousFrom), toDate: isoDate(previousTo) },
  };
}

/**
 * Capa de datos de la home del Manager (Analítica). Posee el estado del rango
 * de fechas y dispara en paralelo `analytics_overview` (ventana actual + previa
 * para deltas), `analytics_funnel`, `analytics_agents` y `analytics_campaigns`.
 * Cada fetch individual tolera su propio fallo (`.catch` → `null`), de modo que
 * un endpoint caído no tumba el resto del panel.
 *
 * @param {object} options
 * @param {object} options.session — sesión admin (lleva el access token)
 * @param {string|undefined} options.tenantId — tenant activo
 * @returns {{ state: object, actions: object }}
 */
export function useManagerAnalyticsData({ session, tenantId }) {
  const [preset, setPreset] = useState(DEFAULT_PRESET);
  const [overview, setOverview] = useState(null);
  const [previousOverview, setPreviousOverview] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [agents, setAgents] = useState(null);
  const [campaigns, setCampaigns] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [sortBy, setSortBy] = useState('revenue_attributed');

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (!tenantId) return undefined;
    let cancelled = false;
    const days = (RANGE_PRESETS.find((p) => p.id === preset) || RANGE_PRESETS[0]).days;
    const { current, previous } = buildRanges(days);

    setLoading(true);
    setError(null);

    Promise.all([
      getAnalyticsOverview(session, tenantId, current).catch(() => null),
      getAnalyticsOverview(session, tenantId, previous).catch(() => null),
      getAnalyticsFunnel(session, tenantId, current).catch(() => null),
      getAnalyticsAgents(session, tenantId, current).catch(() => null),
      getAnalyticsCampaigns(session, tenantId, current).catch(() => null),
    ])
      .then(([ov, prevOv, fnl, ag, cmp]) => {
        if (cancelled) return;
        setOverview(ov);
        setPreviousOverview(prevOv);
        setFunnel(fnl);
        setAgents(ag);
        setCampaigns(cmp);
        if (!ov && !fnl && !ag && !cmp) {
          setError('No se pudo cargar la analítica del negocio.');
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar la analítica del negocio.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session, tenantId, preset, reloadToken]);

  return {
    state: {
      tenantId,
      preset,
      overview,
      previousOverview,
      funnel,
      agents,
      campaigns,
      loading,
      error,
      sortBy,
    },
    actions: {
      setPreset,
      setSortBy,
      refresh,
    },
  };
}
