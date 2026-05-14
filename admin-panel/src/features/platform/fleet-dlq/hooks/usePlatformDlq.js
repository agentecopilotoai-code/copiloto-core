import { useCallback, useEffect, useState } from 'react';

import { getPlatformOutboundDlq } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the cross-tenant Outbound DLQ aggregate from
 * `GET /v1/platform/outbound-dlq`. Re-runs whenever `filters` change (shallow-
 * compared via stringification so callers can freely mutate the local object).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {{windowMinutes?: number, errorCode?: string, tenantId?: string}} options.filters
 * @returns {{
 *   data: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function usePlatformDlq({ session, filters }) {
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
    getPlatformOutboundDlq(session, filters || {})
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el DLQ de la flota');
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, filtersKey, reloadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refresh };
}
