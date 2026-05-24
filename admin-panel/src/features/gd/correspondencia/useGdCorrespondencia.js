/**
 * Hooks Correspondencia interna + externa (GD-UI-0029..0034).
 */
import { useCallback, useEffect, useState } from 'react';

import {
  crearCorrespondenciaInterna,
  listCorrespondencia,
  getCorrespondencia,
  marcarLeidaCorrespondencia,
  responderCorrespondencia,
  reenviarCorrespondencia,
  crearBorradorCorrespondenciaExterna,
  enviarCorrespondenciaARevision,
  revisarCorrespondencia,
  aprobarCorrespondencia,
  firmarCorrespondencia,
  radicarSalidaCorrespondencia,
  enviarCorrespondencia,
  registrarSoporteEnvio,
  agregarDestinatarioCorrespondencia,
  quitarDestinatarioCorrespondencia,
  solicitarAnulacionCorrespondencia,
} from '../services/gdApi.js';

/** useCorrespondenciaList — bandeja interna o externa según filtros. */
export function useCorrespondenciaList(session, filtros = {}) {
  const [state, setState] = useState({
    items: [], total: 0, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!session) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await listCorrespondencia(session, filtros);
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

/** useCorrespondencia — ficha (interna o externa). */
export function useCorrespondencia(session, id, { enabled = true } = {}) {
  const [state, setState] = useState({
    data: null, loading: false, error: null,
  });
  const exec = useCallback(async () => {
    if (!enabled || !session || !id) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await getCorrespondencia(session, id);
      setState({ data, loading: false, error: null });
    } catch (err) {
      setState({ data: null, loading: false, error: err });
    }
  }, [session, id, enabled]);
  useEffect(() => { exec(); }, [exec]);
  return { ...state, refresh: exec };
}

/** Factory para mutators (mismo patrón de PQRSD). */
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

export const useCrearCorrespondenciaInterna = (s) => useMutator(s, crearCorrespondenciaInterna);
export const useCrearBorradorCorrespondenciaExterna = (s) => useMutator(s, crearBorradorCorrespondenciaExterna);
export const useMarcarLeida = (s) => useMutator(s, marcarLeidaCorrespondencia);
export const useResponderCorrespondencia = (s) => useMutator(s, responderCorrespondencia);
export const useReenviarCorrespondencia = (s) => useMutator(s, reenviarCorrespondencia);
export const useEnviarCERevision = (s) => useMutator(s, enviarCorrespondenciaARevision);
export const useRevisarCorrespondencia = (s) => useMutator(s, revisarCorrespondencia);
export const useAprobarCorrespondencia = (s) => useMutator(s, aprobarCorrespondencia);
export const useFirmarCorrespondencia = (s) => useMutator(s, firmarCorrespondencia);
export const useRadicarSalidaCorrespondencia = (s) => useMutator(s, radicarSalidaCorrespondencia);
export const useEnviarCorrespondencia = (s) => useMutator(s, enviarCorrespondencia);
export const useRegistrarSoporteEnvio = (s) => useMutator(s, registrarSoporteEnvio);
export const useAgregarDestinatario = (s) => useMutator(s, agregarDestinatarioCorrespondencia);
export const useQuitarDestinatario = (s) => useMutator(s, quitarDestinatarioCorrespondencia);
export const useSolicitarAnulacionCorrespondencia = (s) => useMutator(s, solicitarAnulacionCorrespondencia);
