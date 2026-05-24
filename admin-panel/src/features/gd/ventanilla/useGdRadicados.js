/**
 * Hooks de Ventanilla Única (GD-UI-0007/0008/0009).
 *
 * Encapsulan llamadas a `/api/v1/gd/ventanilla/*` y exponen state local
 * para cada vista (wizard de entrada, cola de clasificación, salida).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  crearRadicadoEntrada,
  crearRadicadoSalida,
  clasificarRadicado,
  listColaPendientesClasificacion,
  getRadicado,
  reclasificarRadicado,
  corregirDatosMenores,
  solicitarAnulacionRadicado,
  listAnulacionesPendientes,
  aprobarAnulacion,
  rechazarAnulacion,
  buscarRadicados,
  getReportesVentanilla,
  exportarReporteVentanilla,
} from '../services/gdApi.js';

/**
 * useCrearRadicadoEntrada — flujo del wizard (GD-UI-0007).
 *
 * Estado: {submitting, error, radicado}. `submit(payload)` llama al backend
 * y retorna el radicado creado (con numero_radicado + codigo_verificacion).
 */
export function useCrearRadicadoEntrada(session) {
  const [state, setState] = useState({
    submitting: false, error: null, radicado: null,
  });

  const submit = useCallback(async (payload) => {
    setState({ submitting: true, error: null, radicado: null });
    try {
      const radicado = await crearRadicadoEntrada(session, payload);
      setState({ submitting: false, error: null, radicado });
      return radicado;
    } catch (err) {
      setState({ submitting: false, error: err, radicado: null });
      throw err;
    }
  }, [session]);

  const reset = useCallback(() => {
    setState({ submitting: false, error: null, radicado: null });
  }, []);

  return { ...state, submit, reset };
}

/** useCrearRadicadoSalida — análogo (GD-UI-0008). */
export function useCrearRadicadoSalida(session) {
  const [state, setState] = useState({
    submitting: false, error: null, radicado: null,
  });

  const submit = useCallback(async (payload) => {
    setState({ submitting: true, error: null, radicado: null });
    try {
      const radicado = await crearRadicadoSalida(session, payload);
      setState({ submitting: false, error: null, radicado });
      return radicado;
    } catch (err) {
      setState({ submitting: false, error: err, radicado: null });
      throw err;
    }
  }, [session]);

  return { ...state, submit };
}

/**
 * useColaPendientesClasificacion — DataTable de la cola (GD-UI-0009).
 * Fetch + filtros + refresh.
 */
export function useColaPendientesClasificacion(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });

  const fetcher = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listColaPendientesClasificacion(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items,
        total: data?.total ?? items.length,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState({ items: [], total: 0, loading: false, error: err });
    }
    // ESLint exhaustive-deps: filtros es objeto, lo serializamos.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);

  useEffect(() => { fetcher(); }, [fetcher]);

  return { ...state, refresh: fetcher };
}

/**
 * useClasificarRadicado — POST clasificación inicial desde la cola
 * (GD-UI-0009 drawer).
 */
export function useClasificarRadicado(session) {
  const [state, setState] = useState({ submitting: false, error: null });

  const submit = useCallback(async (radicadoId, payload) => {
    setState({ submitting: true, error: null });
    try {
      const result = await clasificarRadicado(session, radicadoId, payload);
      setState({ submitting: false, error: null });
      return result;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session]);

  return { ...state, submit };
}

// ─── UI-3 hooks: ficha + anulación + búsqueda + reportes ──────────────────

/** useGdRadicado — carga ficha por id (GD-UI-0015). */
export function useGdRadicado(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });

  const fetcher = useCallback(async () => {
    if (!enabled || !session || !id) {
      setState((s) => ({ ...s, loading: false }));
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getRadicado(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);

  useEffect(() => { fetcher(); }, [fetcher]);

  return { ...state, refresh: fetcher };
}

/**
 * useReclasificarRadicado / useCorregirDatosMenores — acciones contextuales
 * en la ficha del radicado (GD-UI-0012). Ambas requieren justificación
 * (validado por el server + UI).
 */
export function useReclasificarRadicado(session) {
  const [state, setState] = useState({ submitting: false, error: null });
  const submit = useCallback(async (radicadoId, payload) => {
    setState({ submitting: true, error: null });
    try {
      const r = await reclasificarRadicado(session, radicadoId, payload);
      setState({ submitting: false, error: null });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useCorregirDatosMenores(session) {
  const [state, setState] = useState({ submitting: false, error: null });
  const submit = useCallback(async (radicadoId, payload) => {
    setState({ submitting: true, error: null });
    try {
      const r = await corregirDatosMenores(session, radicadoId, payload);
      setState({ submitting: false, error: null });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/**
 * useSolicitarAnulacion — botón en ficha del radicado (GD-UI-0011).
 */
export function useSolicitarAnulacion(session) {
  const [state, setState] = useState({ submitting: false, error: null });
  const submit = useCallback(async (radicadoId, motivo) => {
    setState({ submitting: true, error: null });
    try {
      const r = await solicitarAnulacionRadicado(session, radicadoId, motivo);
      setState({ submitting: false, error: null });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/**
 * useAnulacionesPendientes — vista de coordinador VU (GD-UI-0011 parte 2).
 * Trae solicitudes pendientes + permite aprobar/rechazar.
 */
export function useAnulacionesPendientes(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });

  const fetcher = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listAnulacionesPendientes(session, filtros);
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

  useEffect(() => { fetcher(); }, [fetcher]);

  const aprobar = useCallback(async (id, observacion) => {
    await aprobarAnulacion(session, id, observacion);
    await fetcher();
  }, [session, fetcher]);

  const rechazar = useCallback(async (id, observacion) => {
    await rechazarAnulacion(session, id, observacion);
    await fetcher();
  }, [session, fetcher]);

  return { ...state, refresh: fetcher, aprobar, rechazar };
}

/** useBuscarRadicados — vista de búsqueda global (GD-UI-0013). */
export function useBuscarRadicados(session, filtros = {}, { enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });

  const fetcher = useCallback(async () => {
    if (!enabled || !session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await buscarRadicados(session, filtros);
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
  }, [session, JSON.stringify(filtros), enabled]);

  useEffect(() => { fetcher(); }, [fetcher]);

  return { ...state, refresh: fetcher };
}

/** useReportesVentanilla — KPIs + tableros (GD-UI-0014). */
export function useReportesVentanilla(session, { desde, hasta, scope } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });

  const fetcher = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getReportesVentanilla(session, { desde, hasta, scope });
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, desde, hasta, scope]);

  useEffect(() => { fetcher(); }, [fetcher]);

  const exportar = useCallback(async (formato = 'csv') => {
    return exportarReporteVentanilla(session, { formato, desde, hasta });
  }, [session, desde, hasta]);

  return { ...state, refresh: fetcher, exportar };
}
