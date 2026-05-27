/**
 * Hooks IA embebida — GD-UI-0072..0078 (EP-010).
 *
 * Cada hook compone un thin-wrapper sobre `gdApi` con manejo
 * homogéneo de loading/error y reintento manual. La política
 * de costos vive server-side (429 + code='ia_budget_exceeded');
 * acá solo propagamos el error para que la UI lo renderice.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  sugerirClasificacionIa, aplicarSugerenciaClasificacion,
  resumirDocumentoIa,
  buscarSemanticoIa, registrarFeedbackBusquedaIa,
  preguntarAsistenteIa, listConversacionesIa, getConversacionIa,
  detectarPiiIa, reportarFalsoPositivoPii,
  getUsoIa, getLimitesIa, actualizarLimitesIa,
  getConfigModelosIa, actualizarConfigModelosIa,
} from '../services/gdApi.js';

/* ───────── GD-UI-0072: Sugerencia clasificación ──────── */

export function useSugerenciaClasificacion(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ data: null, loading: true, error: null });
    try {
      const data = await sugerirClasificacionIa(session, payload);
      setState({ data, loading: false, error: null });
      return data;
    } catch (err) {
      setState({ data: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useAplicarSugerencia(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await aplicarSugerenciaClasificacion(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── GD-UI-0073: Resumen automático ──────── */

export function useResumenDoc(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ data: null, loading: true, error: null });
    try {
      const data = await resumirDocumentoIa(session, payload);
      setState({ data, loading: false, error: null });
      return data;
    } catch (err) {
      setState({ data: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── GD-UI-0074: Búsqueda semántica ──────── */

export function useBusquedaSemantica(session) {
  const [state, setState] = useState({
    resultados: [], modelo: null, tokens: 0,
    loading: false, error: null, lastQuery: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await buscarSemanticoIa(session, payload);
      setState({
        resultados: Array.isArray(data?.resultados) ? data.resultados : [],
        modelo: data?.modelo_embeddings ?? null,
        tokens: data?.tokens ?? 0,
        loading: false, error: null,
        lastQuery: payload?.query ?? null,
      });
      return data;
    } catch (err) {
      setState((s) => ({
        ...s, resultados: [], loading: false, error: err,
      }));
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useFeedbackBusqueda(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await registrarFeedbackBusquedaIa(session, payload);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── GD-UI-0075: Asistente conversacional ──────── */

export function useAsistente(session, conversacionId = null) {
  // mensajes en memoria local + sincroniza con backend cuando se
  // pasa conversacionId al cargar (continuar una conversación).
  const [state, setState] = useState({
    conversacionId, mensajes: [], citasUltima: [],
    loading: false, error: null,
  });
  // Trackeamos qué IDs ya cargamos para no sobreescribir cuando
  // un nuevo ID viene de nuestro propio `enviar` (post mensaje).
  // OJO: NO resetear en render — el reset vive en `reset()` y al
  // crear cualquier ID nuevo desde `enviar` lo añadimos al set.
  const loadedIdsRef = useRef(new Set());
  // Cargar historial si trae conversacionId Y no lo cargamos antes.
  useEffect(() => {
    if (!session || !conversacionId) return;
    if (loadedIdsRef.current.has(conversacionId)) return;
    loadedIdsRef.current.add(conversacionId);
    let alive = true;
    (async () => {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const data = await getConversacionIa(session, conversacionId);
        if (!alive) return;
        setState({
          conversacionId,
          mensajes: Array.isArray(data?.mensajes) ? data.mensajes : [],
          citasUltima: [],
          loading: false, error: null,
        });
      } catch (err) {
        if (!alive) return;
        setState((s) => ({ ...s, loading: false, error: err }));
      }
    })();
    return () => { alive = false; };
  }, [session, conversacionId]);
  const enviar = useCallback(async (mensaje, extras = {}) => {
    if (!session || !mensaje) return null;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await preguntarAsistenteIa(session, {
        conversacion_id: state.conversacionId, mensaje,
        incluir_citas: true, ...extras,
      });
      // Marcar el ID resultante como ya cargado — evita que un caller
      // que sincronice `conversacionId` via prop dispare un reload.
      if (data?.conversacion_id) {
        loadedIdsRef.current.add(data.conversacion_id);
      }
      setState((s) => ({
        ...s,
        conversacionId: data?.conversacion_id ?? s.conversacionId,
        mensajes: [
          ...s.mensajes,
          { rol: 'user', contenido: mensaje },
          { rol: 'assistant', contenido: data?.respuesta ?? '',
            citas: data?.citas ?? [] },
        ],
        citasUltima: Array.isArray(data?.citas) ? data.citas : [],
        loading: false, error: null,
      }));
      return data;
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err }));
      throw err;
    }
  }, [session, state.conversacionId]);
  const reset = useCallback(() => {
    loadedIdsRef.current = new Set();
    setState({
      conversacionId: null, mensajes: [], citasUltima: [],
      loading: false, error: null,
    });
  }, []);
  return { ...state, enviar, reset };
}

export function useConversacionesIa(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listConversacionesIa(session, filtros);
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

/* ───────── GD-UI-0076: Detección PII ──────── */

export function useDeteccionPII(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ data: null, loading: true, error: null });
    try {
      const data = await detectarPiiIa(session, payload);
      setState({ data, loading: false, error: null });
      return data;
    } catch (err) {
      setState({ data: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useFalsoPositivoPii(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await reportarFalsoPositivoPii(session, payload);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── GD-UI-0077: Panel uso IA + costos ──────── */

export function useUsoIa(session, filtros = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getUsoIa(session, filtros);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useLimitesIa(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getLimitesIa(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useActualizarLimitesIa(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await actualizarLimitesIa(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── GD-UI-0078: Configuración modelos IA ──────── */

export function useConfigModelosIa(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getConfigModelosIa(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useActualizarConfigModelosIa(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await actualizarConfigModelosIa(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}
