import { useCallback, useEffect, useState } from 'react';

import { getPlatformRunbooks } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the runbook catalogue from `GET /v1/platform/runbooks`.
 * The catalogue is small (one file per incident type), so search and category
 * filtering happen client-side in the view — this hook just loads the list.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @returns {{
 *   runbooks: Array<object>,
 *   categories: Array<string>,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function useRunbooks({ session }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPlatformRunbooks(session)
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el catálogo de runbooks');
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadToken]);

  return {
    runbooks: data?.runbooks || [],
    categories: data?.categories || [],
    loading,
    error,
    refresh,
  };
}
