import { useCallback, useEffect, useState } from 'react';

import { getPlatformBillingMrr } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the platform-owner Billing / MRR snapshot from
 * `GET /v1/platform/billing/mrr`. The endpoint aggregates the per-tenant
 * subscription model of TASK-0075 across the whole fleet — a point-in-time
 * snapshot, so the caller exposes a manual `refresh` instead of polling.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @returns {{
 *   data: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function usePlatformBilling({ session }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPlatformBillingMrr(session)
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar Billing & MRR');
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadToken]);

  return { data, loading, error, refresh };
}
