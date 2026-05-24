/**
 * Hooks periféricos (GD-UI-0087..0094).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listPerifericos, getPeriferico,
  crearPeriferico, actualizarPeriferico, inactivarPeriferico,
  getEstadoPerifericos,
  imprimirEtiqueta, imprimirConstancia, reimprimir,
  listTrabajosImpresion,
  digitalizarIndividual, digitalizarLote, listColaDigitalizacion,
  asociarDigitalizacionARadicado, reemplazarDigitalizacion,
} from '../services/gdApi.js';

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

// Periféricos
export function usePerifericos(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPerifericos(session, filtros);
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

export function usePeriferico(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPeriferico(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useEstadoPerifericos(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getEstadoPerifericos(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export const useCrearPeriferico = (s) => useMutator(s, crearPeriferico);
export const useActualizarPeriferico = (s) => useMutator(s, actualizarPeriferico);
export const useInactivarPeriferico = (s) => useMutator(s, inactivarPeriferico);

// Impresión
export function useTrabajosImpresion(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listTrabajosImpresion(session, filtros);
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

export const useImprimirEtiqueta = (s) => useMutator(s, imprimirEtiqueta);
export const useImprimirConstancia = (s) => useMutator(s, imprimirConstancia);
export const useReimprimir = (s) => useMutator(s, reimprimir);

// Digitalización
export function useColaDigitalizacion(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listColaDigitalizacion(session, filtros);
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

export const useDigitalizarIndividual = (s) => useMutator(s, digitalizarIndividual);
export const useDigitalizarLote = (s) => useMutator(s, digitalizarLote);
export const useAsociarDigitalizacionARadicado = (s) => useMutator(s, asociarDigitalizacionARadicado);
export const useReemplazarDigitalizacion = (s) => useMutator(s, reemplazarDigitalizacion);
