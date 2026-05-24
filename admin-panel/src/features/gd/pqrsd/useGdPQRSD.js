/**
 * Hooks PQRSD (GD-UI-0020..0024).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listPQRSDFiltrados,
  getPQRSDDashboard,
  getPQRSD,
  asignarDependenciaPQRSD,
  asignarFuncionarioPQRSD,
  reasignarPQRSD,
  proyectarRespuestaPQRSD,
  enviarRespuestaARevision,
  revisarRespuestaPQRSD,
  aprobarRespuestaPQRSD,
  firmarRespuestaPQRSD,
  radicarSalidaRespuesta,
  enviarRespuestaPQRSD,
} from '../services/gdApi.js';

/** usePQRSDDashboard — KPIs del admin (GD-UI-0020). */
export function usePQRSDDashboard(session, params = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPQRSDDashboard(session, params);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(params)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** usePQRSDList — lista filtrable (GD-UI-0021). */
export function usePQRSDList(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPQRSDFiltrados(session, filtros);
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

/** usePQRSD — ficha (GD-UI-0022). */
export function usePQRSD(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPQRSD(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** Helper genérico: hook que envuelve UNA función API mutadora. */
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

// Mutators del workflow.
export const useAsignarDependencia = (s) => useMutator(s, asignarDependenciaPQRSD);
export const useAsignarFuncionario = (s) => useMutator(s, asignarFuncionarioPQRSD);
export const useReasignarPQRSD = (s) => useMutator(s, reasignarPQRSD);
export const useProyectarRespuesta = (s) => useMutator(s, proyectarRespuestaPQRSD);
export const useEnviarARevision = (s) => useMutator(s, enviarRespuestaARevision);
export const useRevisarRespuesta = (s) => useMutator(s, revisarRespuestaPQRSD);
export const useAprobarRespuesta = (s) => useMutator(s, aprobarRespuestaPQRSD);
export const useFirmarRespuesta = (s) => useMutator(s, firmarRespuestaPQRSD);
export const useRadicarSalidaRespuesta = (s) => useMutator(s, radicarSalidaRespuesta);
export const useEnviarRespuesta = (s) => useMutator(s, enviarRespuestaPQRSD);
