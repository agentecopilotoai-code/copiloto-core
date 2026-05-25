/**
 * Hooks admin del sistema GD (GD-UI-0052..0066).
 *
 * Cobertura: usuarios, estructura, catálogos, parámetros, calendario,
 * plantillas de notificación, retención logs, backup, integraciones,
 * seguridad, salud.
 */
import { useCallback, useEffect, useState } from 'react';

import {
  listUsuariosGd, getUsuarioGd, crearUsuarioGd, actualizarUsuarioGd,
  asignarRolUsuarioGd, removerRolUsuarioGd,
  inactivarUsuarioGd, reactivarUsuarioGd,
  getEstructuraOrganica, crearVersionEstructura,
  crearDependencia, actualizarDependencia,
  reubicarDependencia, inactivarDependencia,
  listCatalogos, listItemsCatalogo, crearItemCatalogo,
  actualizarItemCatalogo, inactivarItemCatalogo,
  listParametros, actualizarParametro,
  getCalendarioLaboral, agregarDiaFestivo, quitarDiaFestivo,
  listPlantillasNotificacion, actualizarPlantillaNotificacion,
  probarPlantillaNotificacion,
  getPoliticaRetencionLogs, actualizarPoliticaRetencionLogs,
  getEstadoBackups, dispararBackupManual,
  listIntegraciones, actualizarIntegracion, probarIntegracion,
  getConfigSeguridad, actualizarConfigSeguridad,
  listSesionesActivas, revocarSesion,
  getSaludSistema,
} from '../services/gdApi.js';

// makeListHook recibe un thunk para evitar capturar la referencia al
// momento de carga del módulo — esto permite que pruebas mocks parciales
// (vi.mock con solo algunos endpoints) no rompan en tiempo de import.
function makeListHook(getFn) {
  return function useList(session, filtros = {}) {
    const [state, setState] = useState({
      items: [], total: 0, loading: false, error: null,
    });
    const exec = useCallback(async () => {
      if (!session) return;
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const data = await getFn()(session, filtros);
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
  };
}

function makeReader(getFn) {
  return function useReader(session, { enabled = true } = {}) {
    const [state, setState] = useState({
      data: null, loading: false, error: null,
    });
    const exec = useCallback(async () => {
      if (!enabled || !session) return;
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const data = await getFn()(session);
        setState({ data, loading: false, error: null });
      } catch (err) {
        setState({ data: null, loading: false, error: err });
      }
    }, [session, enabled]);
    useEffect(() => { exec(); }, [exec]);
    return { ...state, refresh: exec };
  };
}

// Usuarios
export const useUsuariosGd = makeListHook(() => listUsuariosGd);
export function useUsuarioGd(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getUsuarioGd(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

// Estructura
export const useEstructuraOrganica = makeReader(() => getEstructuraOrganica);

// Catálogos
export function useCatalogosLista(session) {
  const [state, setState] = useState({ items: [], loading: false, error: null });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listCatalogos(session);
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

export function useItemsCatalogo(session, codigo, { enabled = true } = {}) {
  const [state, setState] = useState({ items: [], loading: false, error: null });
  const exec = useCallback(async () => {
    if (!enabled || !session || !codigo) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listItemsCatalogo(session, codigo);
      const items = Array.isArray(data?.items) ? data.items
        : Array.isArray(data) ? data : [];
      setState({ items, loading: false, error: null });
    } catch (err) {
      setState({ items: [], loading: false, error: err });
    }
  }, [session, codigo, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

// Parámetros
export const useParametros = makeReader(() => listParametros);

// Calendario laboral
export function useCalendarioLaboral(session, anio) {
  const [state, setState] = useState({ data: null, loading: false, error: null });
  const exec = useCallback(async () => {
    if (!session || !anio) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getCalendarioLaboral(session, anio);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, anio]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

// Plantillas de notificación
export function usePlantillasNotificacion(session) {
  const [state, setState] = useState({ items: [], loading: false, error: null });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listPlantillasNotificacion(session);
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

// Retención logs
export const usePoliticaRetencionLogs = makeReader(() => getPoliticaRetencionLogs);

// Backup
export const useEstadoBackups = makeReader(() => getEstadoBackups);

// Integraciones
export function useIntegraciones(session) {
  const [state, setState] = useState({ items: [], loading: false, error: null });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listIntegraciones(session);
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

// Seguridad
export const useConfigSeguridad = makeReader(() => getConfigSeguridad);
export function useSesionesActivas(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listSesionesActivas(session, filtros);
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

// Salud sistema
export const useSaludSistema = makeReader(() => getSaludSistema);

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

// Usuarios
export const useCrearUsuarioGd = (s) => useMutator(s, crearUsuarioGd);
export const useActualizarUsuarioGd = (s) => useMutator(s, actualizarUsuarioGd);
export const useAsignarRolUsuarioGd = (s) => useMutator(s, asignarRolUsuarioGd);
export const useRemoverRolUsuarioGd = (s) => useMutator(s, removerRolUsuarioGd);
export const useInactivarUsuarioGd = (s) => useMutator(s, inactivarUsuarioGd);
export const useReactivarUsuarioGd = (s) => useMutator(s, reactivarUsuarioGd);

// Estructura
export const useCrearVersionEstructura = (s) => useMutator(s, crearVersionEstructura);
export const useCrearDependencia = (s) => useMutator(s, crearDependencia);
export const useActualizarDependencia = (s) => useMutator(s, actualizarDependencia);
export const useReubicarDependencia = (s) => useMutator(s, reubicarDependencia);
export const useInactivarDependencia = (s) => useMutator(s, inactivarDependencia);

// Catálogos
export const useCrearItemCatalogo = (s) => useMutator(s, crearItemCatalogo);
export const useActualizarItemCatalogo = (s) => useMutator(s, actualizarItemCatalogo);
export const useInactivarItemCatalogo = (s) => useMutator(s, inactivarItemCatalogo);

// Parámetros + Calendario
export const useActualizarParametro = (s) => useMutator(s, actualizarParametro);
export const useAgregarDiaFestivo = (s) => useMutator(s, agregarDiaFestivo);
export const useQuitarDiaFestivo = (s) => useMutator(s, quitarDiaFestivo);

// Notificaciones
export const useActualizarPlantillaNotificacion = (s) => useMutator(s, actualizarPlantillaNotificacion);
export const useProbarPlantillaNotificacion = (s) => useMutator(s, probarPlantillaNotificacion);

// Logs / Backup
export const useActualizarPoliticaRetencionLogs = (s) => useMutator(s, actualizarPoliticaRetencionLogs);
export const useDispararBackupManual = (s) => useMutator(s, dispararBackupManual);

// Integraciones
export const useActualizarIntegracion = (s) => useMutator(s, actualizarIntegracion);
export const useProbarIntegracion = (s) => useMutator(s, probarIntegracion);

// Seguridad
export const useActualizarConfigSeguridad = (s) => useMutator(s, actualizarConfigSeguridad);
export const useRevocarSesion = (s) => useMutator(s, revocarSesion);
