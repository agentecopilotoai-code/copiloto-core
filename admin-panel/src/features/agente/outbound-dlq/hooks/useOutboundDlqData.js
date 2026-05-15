import { useCallback, useEffect, useState } from 'react';

import { listOutboundDlq, retryOutboundDlqMessage } from '../../../../services/coreApi.js';

/**
 * Data layer for the Operación · Outbound DLQ view. Owns the failed-message
 * list, the error-code totals, the active error-code filter, the detail-modal
 * selection and the retry handler — extracted verbatim from the legacy
 * `OutboundDLQ` (including the native retry confirm).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useOutboundDlqData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [items, setItems] = useState([]);
  const [totals, setTotals] = useState([]);
  const [errorCodeFilter, setErrorCodeFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [retryingId, setRetryingId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  const loadDlq = useCallback(
    async (filter = '') => {
      if (!tenantId) return;
      setIsLoading(true);
      setNotice(null);
      try {
        const result = await listOutboundDlq(session, tenantId, {
          errorCode: filter || undefined,
          limit: 100,
        });
        setItems(result?.items || []);
        setTotals(result?.totals_by_error_code || []);
        if (!result?.items?.length) {
          setNotice({
            type: 'info',
            text: 'Sin mensajes en la DLQ outbound para los filtros aplicados.',
          });
        }
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'No se pudo cargar la DLQ.' });
      } finally {
        setIsLoading(false);
      }
    },
    [session, tenantId],
  );

  useEffect(() => {
    setErrorCodeFilter('');
    loadDlq('');
  }, [loadDlq]);

  const actions = {
    dismissNotice: () => setNotice(null),
    openDetail: (item) => setSelected(item),
    closeDetail: () => setSelected(null),
    refresh: () => loadDlq(errorCodeFilter),
    toggleFilter: (code) => {
      const next = errorCodeFilter === code ? '' : code;
      setErrorCodeFilter(next);
      loadDlq(next);
    },
    async retry(item) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      if (
        !window.confirm(
          `¿Reintentar envío del mensaje ${String(item.id).slice(0, 8)}…? Volverá a la cola del worker.`,
        )
      ) {
        return;
      }
      setRetryingId(item.id);
      setNotice(null);
      try {
        await retryOutboundDlqMessage(session, tenantId, item.id);
        setNotice({
          type: 'success',
          text: `Mensaje ${String(item.id).slice(0, 8)}… reencolado.`,
        });
        await loadDlq(errorCodeFilter);
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'No se pudo reintentar el envío.' });
      } finally {
        setRetryingId(null);
      }
    },
  };

  return {
    state: {
      tenantId,
      items,
      totals,
      errorCodeFilter,
      selected,
      retryingId,
      isLoading,
      notice,
    },
    actions,
  };
}
