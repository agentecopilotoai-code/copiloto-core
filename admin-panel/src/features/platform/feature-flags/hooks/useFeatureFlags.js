import { useCallback, useEffect, useState } from 'react';

import { getPlatformFeatureFlags } from '../../../../services/coreApi.js';

/**
 * Hook that fetches the read-only feature-flag catalogue from
 * `GET /v1/platform/feature-flags`. The catalogue is a small static registry,
 * so search and type filtering happen client-side in the view.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @returns {{
 *   flags: Array<object>,
 *   flagTypes: Array<string>,
 *   summary: object|null,
 *   note: string|null,
 *   loading: boolean,
 *   error: string|null,
 *   refresh: () => void,
 * }}
 */
export function useFeatureFlags({ session }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPlatformFeatureFlags(session)
      .then((response) => {
        if (cancelled) return;
        setData(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el catálogo de feature flags');
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
    flags: data?.flags || [],
    flagTypes: data?.flag_types || [],
    summary: data?.summary || null,
    note: data?.note || null,
    loading,
    error,
    refresh,
  };
}
