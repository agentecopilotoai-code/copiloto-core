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
