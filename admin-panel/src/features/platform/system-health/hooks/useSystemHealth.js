import { useCallback, useEffect, useState } from 'react';

import { getSystemHealth } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the platform-owner System Health snapshot from
 * `GET /v1/platform/metrics/health`. The endpoint reads the in-process
 * Prometheus registry (TASK-0060) plus a live DB probe — it is a point-in-time
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
export function useSystemHealth({ session }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSystemHealth(session)
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar System Health');
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
