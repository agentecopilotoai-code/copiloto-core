import { useCallback, useEffect, useState } from 'react';

import { listDigestSubscriptions } from '../../../../services/coreApi.js';
import { summarizeSubscriptions } from '../digestReportsData.js';

/**
 * Thin data layer for the Manager · Reportes · Digest view.
 *
 * The relocated `DigestSubscriptionsPanel` keeps owning the CRUD of digest
 * subscriptions self-contained (it manages its own list and refresh). This hook
 * only loads the list once for the orchestrator's summary header (N destinos,
 * X diarios / Y semanales) so the page can show a glance-level summary without
 * duplicating the panel's state.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {string|undefined} options.tenantId — active tenant
 * @returns {{ state: object, actions: object }}
 */
export function useDigestReportsData({ session, tenantId }) {
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (!tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);

    listDigestSubscriptions(session, tenantId)
      .then((data) => {
        if (cancelled) return;
        setSubscriptions(Array.isArray(data?.subscriptions) ? data.subscriptions : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar las suscripciones al digest.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session, tenantId, reloadToken]);

  return {
    state: {
      tenantId,
      subscriptions,
      summary: summarizeSubscriptions(subscriptions),
      loading,
      error,
    },
    actions: { refresh },
  };
}
