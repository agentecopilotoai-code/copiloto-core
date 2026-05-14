import { useCallback, useEffect, useState } from 'react';

import { getAnalyticsOverview } from '../../../../services/coreApi.js';

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

/**
 * Build the current and previous 7-day date ranges. The previous window is the
 * 7 days immediately before the current one, so KPI deltas compare like-for-like.
 */
function buildRanges() {
  const today = new Date();
  const currentFrom = new Date(today);
  currentFrom.setDate(currentFrom.getDate() - 6);
  const previousTo = new Date(today);
  previousTo.setDate(previousTo.getDate() - 7);
  const previousFrom = new Date(today);
  previousFrom.setDate(previousFrom.getDate() - 13);
  return {
    current: { fromDate: isoDate(currentFrom), toDate: isoDate(today) },
    previous: { fromDate: isoDate(previousFrom), toDate: isoDate(previousTo) },
  };
}

/**
 * Hook that loads the Owner/Admin dashboard data: `analytics_overview` for the
 * current 7-day window and the prior 7-day window (so KPI cards can show a
 * week-over-week delta).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|undefined} options.tenantId — active tenant id
 * @returns {{
 *   current: object|null,
 *   previous: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function useDashboardData({ session, tenantId }) {
  const [current, setCurrent] = useState(null);
  const [previous, setPrevious] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (!tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const { current: currentRange, previous: previousRange } = buildRanges();
    Promise.all([
      getAnalyticsOverview(session, tenantId, currentRange),
      getAnalyticsOverview(session, tenantId, previousRange),
    ])
      .then(([cur, prev]) => {
        if (cancelled) return;
        setCurrent(cur || null);
        setPrevious(prev || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el dashboard');
        setCurrent(null);
        setPrevious(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, reloadToken]);

  return { current, previous, loading, error, refresh };
}
