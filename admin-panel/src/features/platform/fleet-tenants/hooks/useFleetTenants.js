import { useCallback, useEffect, useState } from 'react';

import { listFleetTenants } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the platform-owner fleet view of tenants from
 * `GET /v1/tenants`. Re-runs whenever `filters` change (shallow-compared via
 * stringification so callers can freely mutate the local object).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {{status?: string, country?: string, vertical?: string, search?: string, limit?: number, offset?: number}} options.filters
 * @returns {{
 *   items: Array<object>,
 *   total: number,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void
 * }}
 */
export function useFleetTenants({ session, filters }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const filtersKey = JSON.stringify(filters || {});

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listFleetTenants(session, filters || {})
      .then((response) => {
        if (cancelled) return;
        setItems(Array.isArray(response?.items) ? response.items : []);
        setTotal(Number(response?.total) || 0);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar la flota');
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, filtersKey, reloadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return { items, total, loading, error, refresh };
}
