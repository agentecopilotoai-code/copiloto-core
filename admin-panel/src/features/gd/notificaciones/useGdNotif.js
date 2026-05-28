/**
 * Hooks Notificaciones + Alertas críticas — EP-012 (UI-13 /
 * GD-UI-0081..0083).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listNotificacionesInbox, marcarNotifLeida, marcarNotifsTodasLeidas,
  getPreferenciasNotif, actualizarPreferenciasNotif,
  listAlertasCriticas, atenderAlertaCritica,
} from '../services/gdApi.js';

/* ───────── Inbox notificaciones ──────── */

export function useNotificacionesInbox(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, noLeidas: 0,
    loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listNotificacionesInbox(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items, total: data?.total ?? items.length,
        noLeidas: data?.no_leidas ?? items.filter((n) => !n.leida).length,
        loading: false, error: null,
      });
    } catch (err) {
      setState({
        items: [], total: 0, noLeidas: 0,
        loading: false, error: err,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useMarcarNotifLeida(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (id) => {
    if (!session || !id) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await marcarNotifLeida(session, id);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useMarcarTodasLeidas(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async () => {
    if (!session) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await marcarNotifsTodasLeidas(session);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── Preferencias notificaciones ──────── */

export function usePreferenciasNotif(session) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getPreferenciasNotif(session);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useActualizarPreferenciasNotif(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await actualizarPreferenciasNotif(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── Alertas críticas ──────── */

export function useAlertasCriticas(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], totalPendientes: 0,
    loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listAlertasCriticas(session, filtros);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({
        items,
        totalPendientes: data?.total_pendientes ??
          items.filter((a) => !a.atendida_por).length,
        loading: false, error: null,
      });
    } catch (err) {
      setState({
        items: [], totalPendientes: 0,
        loading: false, error: err,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, JSON.stringify(filtros)]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useAtenderAlerta(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (id, comentario) => {
    if (!session || !id) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await atenderAlertaCritica(session, id, comentario);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}
