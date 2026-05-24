/**
 * Hooks de Buzón (GD-UI-0016..0019).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  getMiBuzon,
  getBuzonDependencia,
  getCargaEquipo,
  getTarea,
  ejecutarAccionTarea,
  listUsuariosDependencia,
  getTareasPendientesUsuario,
  reasignarTareasLote,
} from '../services/gdApi.js';

export const CARPETAS = Object.freeze([
  { id: 'pqrsd', label: 'PQRSD asignadas', icon: '📨' },
  { id: 'correspondencia_in', label: 'Correspondencia recibida', icon: '📥' },
  { id: 'correspondencia_out', label: 'Correspondencia enviada', icon: '📤' },
  { id: 'tareas', label: 'Tareas pendientes', icon: '✅' },
  { id: 'borradores', label: 'Borradores', icon: '📝' },
  { id: 'docs_revisar', label: 'Documentos por revisar', icon: '🔍' },
  { id: 'docs_aprobar', label: 'Documentos por aprobar', icon: '👁️' },
  { id: 'docs_firmar', label: 'Documentos por firmar', icon: '✍️' },
  { id: 'notificaciones', label: 'Notificaciones', icon: '🔔' },
  { id: 'alertas', label: 'Alertas', icon: '⚠️' },
]);

/**
 * useBuzon — hook genérico para Mi Buzón / Buzón Dependencia.
 * `fetcher` es la función gdApi a llamar (getMiBuzon o getBuzonDependencia).
 */
function useBuzon(fetcher, session, { carpeta, scope, limit = 50 } = {}) {
  const [state, setState] = useState({
    items: [], contadores: {}, total: 0,
    loading: false, error: null,
  });

  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fetcher(session, { carpeta, scope, limit });
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items,
        contadores: data?.contadores || {},
        total: data?.total ?? items.length,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState({ items: [], contadores: {}, total: 0, loading: false, error: err });
    }
  }, [fetcher, session, carpeta, scope, limit]);

  useEffect(() => { exec(); }, [exec]);

  return { ...state, refresh: exec };
}

export function useMiBuzon(session, opts) {
  return useBuzon(getMiBuzon, session, opts);
}

export function useBuzonDependencia(session, opts) {
  return useBuzon(getBuzonDependencia, session, opts);
}

/** useCargaEquipo — KPIs por usuario en la dependencia (jefe/secretario). */
export function useCargaEquipo(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getCargaEquipo(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** useTarea — ficha de tarea. */
export function useTarea(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getTarea(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** useAccionTarea — submitter genérico de acciones del workflow. */
export function useAccionTarea(session) {
  const [state, setState] = useState({ submitting: false, error: null });
  const submit = useCallback(async (id, accion, payload) => {
    setState({ submitting: true, error: null });
    try {
      const r = await ejecutarAccionTarea(session, id, accion, payload);
      setState({ submitting: false, error: null });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/** useUsuariosDependencia — para UsuarioPicker. */
export function useUsuariosDependencia(session, dependenciaId, { rol, enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !dependenciaId) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listUsuariosDependencia(session, dependenciaId, { rol });
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session, dependenciaId, rol, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** useTareasPendientesUsuario — para el wizard de reasignación masiva. */
export function useTareasPendientesUsuario(session, userId, { enabled = true } = {}) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !userId) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getTareasPendientesUsuario(session, userId);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session, userId, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** useReasignarTareasLote — submit del wizard. */
export function useReasignarTareasLote(session) {
  const [state, setState] = useState({ submitting: false, error: null, result: null });
  const submit = useCallback(async (userId, payload) => {
    setState({ submitting: true, error: null, result: null });
    try {
      const r = await reasignarTareasLote(session, userId, payload);
      setState({ submitting: false, error: null, result: r });
      return r;
    } catch (err) {
      setState({ submitting: false, error: err, result: null });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}
