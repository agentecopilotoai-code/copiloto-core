/**
 * Hooks Correo institucional — EP-011 (UI-13 / GD-UI-0079..0080,
 * 0084..0086).
 *
 * Cubre los 5 sub-flujos:
 *  - Bandeja entrante + preview + convertir-a-radicado / descartar.
 *  - Composer saliente (plantillas + adjuntos).
 *  - Config canales SMTP/IMAP/POP3 + test conectividad.
 *  - Reglas de auto-clasificación (CRUD).
 *  - Salud canal correo (latencias, bounces, errores).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listCorreoEntrante, getCorreoEntrante,
  convertirCorreoARadicado, descartarCorreo,
  enviarCorreoSaliente, listPlantillasCorreo,
  listConfigCanalesEmail, actualizarConfigCanalEmail, probarCanalEmail,
  listReglasAutoClasif, crearReglaAutoClasif,
  actualizarReglaAutoClasif, eliminarReglaAutoClasif,
  getSaludCorreo,
} from '../services/gdApi.js';

/* ───────── Bandeja correo entrante ──────── */

export function useCorreoEntrante(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listCorreoEntrante(session, filtros);
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

export function useCorreoEntranteItem(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getCorreoEntrante(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useConvertirARadicado(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (id, payload) => {
    if (!session || !id) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await convertirCorreoARadicado(session, id, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useDescartarCorreo(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (id, motivo) => {
    if (!session || !id) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await descartarCorreo(session, id, motivo);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── Composer saliente ──────── */

export function useCorreoComposer(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await enviarCorreoSaliente(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function usePlantillasCorreo(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPlantillasCorreo(session);
      setState({
        items: Array.isArray(data?.items) ? data.items
          : Array.isArray(data) ? data : [],
        loading: false, error: null,
      });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/* ───────── Config canales email ──────── */

export function useConfigCanalesEmail(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listConfigCanalesEmail(session);
      setState({
        items: Array.isArray(data?.items) ? data.items
          : Array.isArray(data) ? data : [],
        loading: false, error: null,
      });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useActualizarCanalEmail(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (id, payload) => {
    if (!session || !id) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await actualizarConfigCanalEmail(session, id, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useProbarCanalEmail(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (id) => {
    if (!session || !id) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await probarCanalEmail(session, id);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── Reglas auto-clasificación ──────── */

export function useReglasAutoClasif(session) {
  const [state, setState] = useState({
    items: [], loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listReglasAutoClasif(session);
      setState({
        items: Array.isArray(data?.items) ? data.items
          : Array.isArray(data) ? data : [],
        loading: false, error: null,
      });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

export function useCrearReglaAutoClasif(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (payload) => {
    if (!session) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await crearReglaAutoClasif(session, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useActualizarReglaAutoClasif(session) {
  const [state, setState] = useState({
    result: null, loading: false, error: null,
  });
  const submit = useCallback(async (id, payload) => {
    if (!session || !id) return null;
    setState({ result: null, loading: true, error: null });
    try {
      const result = await actualizarReglaAutoClasif(session, id, payload);
      setState({ result, loading: false, error: null });
      return result;
    } catch (err) {
      setState({ result: null, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

export function useEliminarReglaAutoClasif(session) {
  const [state, setState] = useState({
    enviado: false, loading: false, error: null,
  });
  const submit = useCallback(async (id) => {
    if (!session || !id) return null;
    setState({ enviado: false, loading: true, error: null });
    try {
      await eliminarReglaAutoClasif(session, id);
      setState({ enviado: true, loading: false, error: null });
      return true;
    } catch (err) {
      setState({ enviado: false, loading: false, error: err });
      throw err;
    }
  }, [session]);
  return { ...state, submit };
}

/* ───────── Salud del canal correo ──────── */

export function useSaludCorreo(session, ventana = '24h') {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getSaludCorreo(session, ventana);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, ventana]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}
