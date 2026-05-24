/**
 * Hooks Plantillas (GD-UI-0039/0040).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listPlantillas,
  getPlantilla,
  crearPlantilla,
  actualizarPlantilla,
  nuevaVersionPlantilla,
  inactivarPlantilla,
  generarDocumentoDePlantilla,
} from '../services/gdApi.js';

export function usePlantillasList(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPlantillas(session, filtros);
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

export function usePlantilla(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPlantilla(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
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

export const useCrearPlantilla = (s) => useMutator(s, crearPlantilla);
export const useActualizarPlantilla = (s) => useMutator(s, actualizarPlantilla);
export const useNuevaVersionPlantilla = (s) => useMutator(s, nuevaVersionPlantilla);
export const useInactivarPlantilla = (s) => useMutator(s, inactivarPlantilla);
export const useGenerarDocumentoDePlantilla = (s) => useMutator(s, generarDocumentoDePlantilla);
