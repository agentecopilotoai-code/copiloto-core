/**
 * Hooks Firmas (GD-UI-0041..0044).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listPorFirmar,
  getEvidenciaFirma,
  registrarFirmaEscaneada,
  firmarDocumento,
  rechazarFirmaDocumento,
  listFirmantesAutorizados,
  crearFirmanteAutorizado,
  actualizarFirmanteAutorizado,
  inactivarFirmanteAutorizado,
} from '../services/gdApi.js';

export function usePorFirmar(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPorFirmar(session, filtros);
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

export function useEvidenciaFirma(session, firmaId, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !firmaId) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getEvidenciaFirma(session, firmaId);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, firmaId, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useFirmantesAutorizados(session, { enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listFirmantesAutorizados(session);
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

export const useRegistrarFirmaEscaneada = (s) => useMutator(s, registrarFirmaEscaneada);
export const useFirmarDocumento = (s) => useMutator(s, firmarDocumento);
export const useRechazarFirmaDocumento = (s) => useMutator(s, rechazarFirmaDocumento);
export const useCrearFirmanteAutorizado = (s) => useMutator(s, crearFirmanteAutorizado);
export const useActualizarFirmanteAutorizado = (s) => useMutator(s, actualizarFirmanteAutorizado);
export const useInactivarFirmanteAutorizado = (s) => useMutator(s, inactivarFirmanteAutorizado);
