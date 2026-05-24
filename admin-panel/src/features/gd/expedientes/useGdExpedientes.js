/**
 * Hooks expedientes electrónicos (GD-UI-0049..0051).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listExpedientes, getExpediente, crearExpediente, actualizarExpediente,
  listDocumentosExpediente, agregarDocumentoExpediente,
  quitarDocumentoExpediente, cerrarExpediente, transferirExpediente,
  reabrirExpediente, getIndiceExpediente, getActaCierreExpediente,
  buscarExpedientes,
} from '../services/gdApi.js';

export function useExpedientesList(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listExpedientes(session, filtros);
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

export function useExpediente(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getExpediente(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useDocumentosExpediente(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listDocumentosExpediente(session, id);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useIndiceExpediente(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getIndiceExpediente(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useActaCierreExpediente(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getActaCierreExpediente(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useBuscarExpedientes(session) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null, ran: false,
  });
  const buscar = useCallback(async (filtros) => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await buscarExpedientes(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items, total: data?.total ?? items.length,
        loading: false, error: null, ran: true,
      });
    } catch (err) {
      setState({ items: [], total: 0, loading: false, error: err, ran: true });
    }
  }, [session]);
  return { ...state, buscar };
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

export const useCrearExpediente = (s) => useMutator(s, crearExpediente);
export const useActualizarExpediente = (s) => useMutator(s, actualizarExpediente);
export const useAgregarDocumentoExp = (s) => useMutator(s, agregarDocumentoExpediente);
export const useQuitarDocumentoExp = (s) => useMutator(s, quitarDocumentoExpediente);
export const useCerrarExpediente = (s) => useMutator(s, cerrarExpediente);
export const useTransferirExpediente = (s) => useMutator(s, transferirExpediente);
export const useReabrirExpediente = (s) => useMutator(s, reabrirExpediente);
