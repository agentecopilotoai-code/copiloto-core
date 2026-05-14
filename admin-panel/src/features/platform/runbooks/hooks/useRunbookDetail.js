import { useEffect, useState } from 'react';

import { getPlatformRunbook } from '../../../../services/coreApi.js';

/**
 * Hook that fetches one runbook rendered to safe HTML from
 * `GET /v1/platform/runbooks/{slug}`. Re-runs whenever `slug` changes; a null
 * `slug` clears the state (no request fired).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|null} options.slug — the selected runbook slug
 * @returns {{ runbook: object|null, loading: boolean, error: string|null }}
 */
export function useRunbookDetail({ session, slug }) {
  const [runbook, setRunbook] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!slug) {
      setRunbook(null);
      setError(null);
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRunbook(null);
    getPlatformRunbook(session, slug)
      .then((response) => {
        if (cancelled) return;
        setRunbook(response || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el runbook');
        setRunbook(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, slug]);

  return { runbook, loading, error };
}
