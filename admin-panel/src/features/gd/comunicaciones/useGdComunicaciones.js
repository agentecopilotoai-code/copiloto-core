/**
 * Hooks correo importado + notificaciones + alertas (GD-UI-0079..0086).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listCorreosImportados, getCorreoImportado,
  convertirCorreoARadicado, descartarCorreo,
  listMisNotificaciones, marcarNotificacionLeida,
  marcarTodasNotificacionesLeidas,
  getPreferenciasNotificaciones, actualizarPreferenciasNotificaciones,
  listAlertas, atenderAlerta,
  listReglasAlerta, crearReglaAlerta, actualizarReglaAlerta,
  inactivarReglaAlerta,
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

// Correo importado
export function useCorreosImportados(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listCorreosImportados(session, filtros);
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

export function useCorreoImportado(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getCorreoImportado(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export const useConvertirCorreoARadicado = (s) => useMutator(s, convertirCorreoARadicado);
export const useDescartarCorreo = (s) => useMutator(s, descartarCorreo);

// Notificaciones
export function useMisNotificaciones(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, no_leidas: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listMisNotificaciones(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items, total: data?.total ?? items.length,
        no_leidas: data?.no_leidas ?? items.filter((n) => !n.leida).length,
        loading: false, error: null,
      });
    } catch (err) {
      setState({ items: [], total: 0, no_leidas: 0, loading: false, error: err });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export const useMarcarNotificacionLeida = (s) => useMutator(s, marcarNotificacionLeida);
export const useMarcarTodasLeidas = (s) => useMutator(s, marcarTodasNotificacionesLeidas);

export function usePreferenciasNotificaciones(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPreferenciasNotificaciones(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export const useActualizarPreferenciasNotificaciones = (s) =>
  useMutator(s, actualizarPreferenciasNotificaciones);

// Alertas
export function useAlertas(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listAlertas(session, filtros);
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

export const useAtenderAlerta = (s) => useMutator(s, atenderAlerta);

export function useReglasAlerta(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listReglasAlerta(session);
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

export const useCrearReglaAlerta = (s) => useMutator(s, crearReglaAlerta);
export const useActualizarReglaAlerta = (s) => useMutator(s, actualizarReglaAlerta);
export const useInactivarReglaAlerta = (s) => useMutator(s, inactivarReglaAlerta);
