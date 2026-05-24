/**
 * Hooks auditoría + reportes consolidados (GD-UI-0067..0071).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  buscarAuditoria, getEventoAuditoria, exportarAuditoria,
  listCatalogoEntidadesAuditoria, listCatalogoAccionesAuditoria,
  getReportesConsolidados, exportarReporteConsolidado,
  exportarReporteEjecutivoPdf,
  getResumenIntegridadAuditor, verificarHashRegistro,
} from '../services/gdApi.js';

export function useAuditoriaBandeja(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await buscarAuditoria(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items, total: data?.total ?? items.length,
        loading: false, error: null,
      });
    } catch (err) {
      setState({ items: [], total: 0, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useEventoAuditoria(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getEventoAuditoria(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useCatalogosAuditoria(session) {
  const [state, setState] = useState({
    entidades: [], acciones: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [e, a] = await Promise.all([
        listCatalogoEntidadesAuditoria(session),
        listCatalogoAccionesAuditoria(session),
      ]);
      setState({
        entidades: Array.isArray(e?.items) ? e.items : (Array.isArray(e) ? e : []),
        acciones: Array.isArray(a?.items) ? a.items : (Array.isArray(a) ? a : []),
        loading: false, error: null,
      });
    } catch (err) {
      setState({ entidades: [], acciones: [], loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useReportesConsolidados(session, filtros = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getReportesConsolidados(session, filtros);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useResumenIntegridadAuditor(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getResumenIntegridadAuditor(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

function useMutator(session, fn) {
  const [state, setState] = useState({ submitting: false, error: null });
  const submit = useCallback(async (...args) => {
    setState({ submitting: true, error: null });
    try {
      const r = await fn(session, ...args);
      setState({ submitting: false, error: null });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session, fn]);
  return { ...state, submit };
}

export const useExportarAuditoria = (s) => useMutator(s, exportarAuditoria);
export const useExportarReporteConsolidado = (s) =>
  useMutator(s, exportarReporteConsolidado);
export const useExportarReporteEjecutivoPdf = (s) =>
  useMutator(s, exportarReporteEjecutivoPdf);
export const useVerificarHashRegistro = (s) =>
  useMutator(s, verificarHashRegistro);
