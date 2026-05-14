import { useCallback, useEffect, useState } from 'react';

import { getPlatformIncidents } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the platform-owner incidents feed from
 * `GET /v1/platform/incidents`. Re-runs whenever `filters` change (shallow-
 * compared via stringification so callers can freely mutate the local object).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {{status?: string, kind?: string, limit?: number}} options.filters
 * @returns {{
 *   incidents: Array<object>,
 *   summary: object,
 *   note: string|null,
 *   generatedAt: string|null,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function usePlatformIncidents({ session, filters }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const filtersKey = JSON.stringify(filters || {});

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPlatformIncidents(session, filters || {})
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar Incidentes');
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, filtersKey, reloadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    incidents: data?.incidents || [],
    summary: data?.summary || null,
    note: data?.note || null,
    generatedAt: data?.generated_at || null,
    loading,
    error,
    refresh,
  };
}
