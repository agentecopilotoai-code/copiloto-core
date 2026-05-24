/**
 * Hooks TRD/TVD + clasificación (GD-UI-0045..0048).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listTRD, getSerie, getTRDVersionActual, listVersionesTRD,
  crearSerie, actualizarSerie, eliminarSerie,
  crearSubserie, crearTipoDocumental,
  nuevaVersionTRD, aprobarVersionTRD,
  listTVD, actualizarTVD,
  clasificarConTRD,
} from '../services/gdApi.js';

export function useTRD(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listTRD(session, filtros);
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

export function useSerie(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getSerie(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useTRDVersionActual(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getTRDVersionActual(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useVersionesTRD(session, { enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listVersionesTRD(session);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useTVD(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listTVD(session, filtros);
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

export const useCrearSerie = (s) => useMutator(s, crearSerie);
export const useActualizarSerie = (s) => useMutator(s, actualizarSerie);
export const useEliminarSerie = (s) => useMutator(s, eliminarSerie);
export const useCrearSubserie = (s) => useMutator(s, crearSubserie);
export const useCrearTipoDocumental = (s) => useMutator(s, crearTipoDocumental);
export const useNuevaVersionTRD = (s) => useMutator(s, nuevaVersionTRD);
export const useAprobarVersionTRD = (s) => useMutator(s, aprobarVersionTRD);
export const useActualizarTVD = (s) => useMutator(s, actualizarTVD);
export const useClasificarConTRD = (s) => useMutator(s, clasificarConTRD);
