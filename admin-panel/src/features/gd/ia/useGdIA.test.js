import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  sugerirClasificacionIA: vi.fn(),
  feedbackSugerenciaClasificacionIA: vi.fn(),
  generarResumenIA: vi.fn(),
  buscarSemanticoIA: vi.fn(),
  enviarMensajeAsistenteIA: vi.fn(),
  listConversacionesAsistente: vi.fn(),
  getConversacionAsistente: vi.fn(),
  detectarPiiIA: vi.fn(),
  listAlertasPii: vi.fn(),
  marcarAlertaPiiAtendida: vi.fn(),
  getUsoIA: vi.fn(),
  getConfigModelosIA: vi.fn(),
  actualizarConfigModelosIA: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useSugerirClasificacionIA, useFeedbackSugerenciaIA,
  useGenerarResumenIA, useBusquedaSemanticaIA,
  useEnviarMensajeAsistente, useConversacionesAsistente,
  useConversacionAsistente,
  useDetectarPiiIA, useAlertasPii, useMarcarAlertaPiiAtendida,
  useUsoIA, useConfigModelosIA, useActualizarConfigModelosIA,
} from './useGdIA.js';

const S = { token: 't' };

describe('mutators IA', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['sugerir', useSugerirClasificacionIA, 'sugerirClasificacionIA'],
    ['feedback', useFeedbackSugerenciaIA, 'feedbackSugerenciaClasificacionIA'],
    ['resumen', useGenerarResumenIA, 'generarResumenIA'],
    ['enviarMsg', useEnviarMensajeAsistente, 'enviarMensajeAsistenteIA'],
    ['detectarPii', useDetectarPiiIA, 'detectarPiiIA'],
    ['atenderPii', useMarcarAlertaPiiAtendida, 'marcarAlertaPiiAtendida'],
    ['actCfg', useActualizarConfigModelosIA, 'actualizarConfigModelosIA'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ ok: true });
  });
  it('propaga error', async () => {
    api.sugerirClasificacionIA.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useSugerirClasificacionIA(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
  });
});

describe('useBusquedaSemanticaIA', () => {
  beforeEach(() => vi.clearAllMocks());
  it('busca + setea ran', async () => {
    api.buscarSemanticoIA.mockResolvedValue({ items: [{ id: 'd1' }] });
    const { result } = renderHook(() => useBusquedaSemanticaIA(S));
    expect(result.current.ran).toBe(false);
    await act(async () => { await result.current.buscar({ q: 'hola' }); });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.ran).toBe(true);
    expect(result.current.query).toBe('hola');
  });
  it('array directo', async () => {
    api.buscarSemanticoIA.mockResolvedValue([{ id: 'd1' }]);
    const { result } = renderHook(() => useBusquedaSemanticaIA(S));
    await act(async () => { await result.current.buscar({ q: 'a' }); });
    expect(result.current.items).toHaveLength(1);
  });
  it('error', async () => {
    api.buscarSemanticoIA.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useBusquedaSemanticaIA(S));
    await act(async () => { await result.current.buscar({ q: 'x' }); });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session no-op', async () => {
    const { result } = renderHook(() => useBusquedaSemanticaIA(null));
    await act(async () => { await result.current.buscar({ q: 'x' }); });
    expect(api.buscarSemanticoIA).not.toHaveBeenCalled();
  });
});

describe('useConversacionesAsistente + useConversacionAsistente', () => {
  beforeEach(() => vi.clearAllMocks());
  it('lista', async () => {
    api.listConversacionesAsistente.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useConversacionesAsistente(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('lista items+total', async () => {
    api.listConversacionesAsistente.mockResolvedValue({ items: [{ id: 'c1' }] });
    const { result } = renderHook(() => useConversacionesAsistente(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('lista error', async () => {
    api.listConversacionesAsistente.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConversacionesAsistente(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('conv individual carga', async () => {
    api.getConversacionAsistente.mockResolvedValue({ id: 'c1', mensajes: [] });
    const { result } = renderHook(() => useConversacionAsistente(S, 'c1'));
    await waitFor(() => expect(result.current.data?.id).toBe('c1'));
  });
  it('conv disabled', () => {
    renderHook(() => useConversacionAsistente(S, 'c1', { enabled: false }));
    expect(api.getConversacionAsistente).not.toHaveBeenCalled();
  });
  it('conv error', async () => {
    api.getConversacionAsistente.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConversacionAsistente(S, 'c1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useAlertasPii + useUsoIA + useConfigModelosIA', () => {
  beforeEach(() => vi.clearAllMocks());
  it('alertas items+total', async () => {
    api.listAlertasPii.mockResolvedValue({ items: [{ id: 'a1' }], total: 1 });
    const { result } = renderHook(() => useAlertasPii(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('alertas array', async () => {
    api.listAlertasPii.mockResolvedValue([{ id: 'a1' }]);
    const { result } = renderHook(() => useAlertasPii(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('alertas error', async () => {
    api.listAlertasPii.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAlertasPii(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('alertas sin session', () => {
    renderHook(() => useAlertasPii(null));
    expect(api.listAlertasPii).not.toHaveBeenCalled();
  });
  it('uso carga', async () => {
    api.getUsoIA.mockResolvedValue({ total_llamadas: 100 });
    const { result } = renderHook(() => useUsoIA(S));
    await waitFor(() => expect(result.current.data?.total_llamadas).toBe(100));
  });
  it('uso error', async () => {
    api.getUsoIA.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useUsoIA(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('uso sin session', () => {
    renderHook(() => useUsoIA(null));
    expect(api.getUsoIA).not.toHaveBeenCalled();
  });
  it('config carga', async () => {
    api.getConfigModelosIA.mockResolvedValue({ asistente: { modelo: 'gpt' } });
    const { result } = renderHook(() => useConfigModelosIA(S));
    await waitFor(() => expect(result.current.data?.asistente?.modelo).toBe('gpt'));
  });
  it('config error', async () => {
    api.getConfigModelosIA.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConfigModelosIA(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});
