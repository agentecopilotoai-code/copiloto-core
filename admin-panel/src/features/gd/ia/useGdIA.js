/**
 * Hooks IA embebida (GD-UI-0072..0078).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  sugerirClasificacionIA, feedbackSugerenciaClasificacionIA,
  generarResumenIA, buscarSemanticoIA,
  enviarMensajeAsistenteIA, listConversacionesAsistente,
  getConversacionAsistente,
  detectarPiiIA, listAlertasPii, marcarAlertaPiiAtendida,
  getUsoIA, getConfigModelosIA, actualizarConfigModelosIA,
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

// Sugerencia clasificación (mutator → ejecuta a demanda)
export const useSugerirClasificacionIA = (s) => useMutator(s, sugerirClasificacionIA);
export const useFeedbackSugerenciaIA = (s) => useMutator(s, feedbackSugerenciaClasificacionIA);

// Resumen
export const useGenerarResumenIA = (s) => useMutator(s, generarResumenIA);

// Búsqueda semántica
export function useBusquedaSemanticaIA(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null, ran: false, query: '',
  });
  const buscar = useCallback(async (payload) => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null, query: payload?.q || '' }));
    try {
      const data = await buscarSemanticoIA(session, payload);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null, ran: true, query: payload?.q || '' });
    } catch (err) {
      setState({ items: [], loading: false, error: err, ran: true, query: payload?.q || '' });
    }
  }, [session]);
  return { ...state, buscar };
}

// Asistente conversacional
export const useEnviarMensajeAsistente = (s) => useMutator(s, enviarMensajeAsistenteIA);

export function useConversacionesAsistente(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listConversacionesAsistente(session);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useConversacionAsistente(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getConversacionAsistente(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

// PII
export const useDetectarPiiIA = (s) => useMutator(s, detectarPiiIA);
export const useMarcarAlertaPiiAtendida = (s) => useMutator(s, marcarAlertaPiiAtendida);

export function useAlertasPii(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listAlertasPii(session, filtros);
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

// Uso + costos
export function useUsoIA(session, filtros = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getUsoIA(session, filtros);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

// Configuración modelos
export function useConfigModelosIA(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getConfigModelosIA(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export const useActualizarConfigModelosIA = (s) => useMutator(s, actualizarConfigModelosIA);
