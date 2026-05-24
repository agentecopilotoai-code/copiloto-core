/**
 * useGdAudit — hook genérico para timeline de auditoría de una entidad GD.
 *
 * Consume `GET /api/v1/core/auditoria?entidad_tipo=<tipo>&entidad_id=<uuid>`.
 * Devuelve `{events, loading, error, refresh}`.
 *
 * Cualquier ficha del módulo (Radicado, PQRSD, Documento, Correspondencia,
 * Expediente, Usuario) la usa para alimentar `<WorkflowTimeline />`.
 */
import { useCallback, useEffect, useState } from 'react';

import { listAuditoria } from '../services/gdApi.js';

export function useGdAudit({ session, entidadTipo, entidadId, limit = 50, enabled = true }) {
  const [state, setState] = useState({ events: [], loading: false, error: null });

  const fetcher = useCallback(async () => {
    if (!enabled || !session || !entidadTipo || !entidadId) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listAuditoria(session, {
        entidadTipo,
        entidadId,
        limit,
      });
      const items = Array.isArray(data?.items) ? data.items : [];
      setState({ events: items, loading: false, error: null });
    } catch (err) {
      setState({ events: [], loading: false, error: err });
    }
  }, [session, entidadTipo, entidadId, limit, enabled]);

  useEffect(() => {
    fetcher();
  }, [fetcher]);

  return { ...state, refresh: fetcher };
}
