import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listTRD: vi.fn(),
  getSerie: vi.fn(),
  getTRDVersionActual: vi.fn(),
  listVersionesTRD: vi.fn(),
  crearSerie: vi.fn(),
  actualizarSerie: vi.fn(),
  eliminarSerie: vi.fn(),
  crearSubserie: vi.fn(),
  crearTipoDocumental: vi.fn(),
  nuevaVersionTRD: vi.fn(),
  aprobarVersionTRD: vi.fn(),
  listTVD: vi.fn(),
  actualizarTVD: vi.fn(),
  clasificarConTRD: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useTRD, useSerie, useTRDVersionActual, useVersionesTRD, useTVD,
  useCrearSerie, useActualizarSerie, useEliminarSerie,
  useCrearSubserie, useCrearTipoDocumental,
  useNuevaVersionTRD, useAprobarVersionTRD,
  useActualizarTVD, useClasificarConTRD,
} from './useGdTRD.js';

const S = { token: 't' };

describe('useTRD', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items+total', async () => {
    api.listTRD.mockResolvedValue({ items: [{ id: 's1' }], total: 1 });
    const { result } = renderHook(() => useTRD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array directo', async () => {
    api.listTRD.mockResolvedValue([{ id: 's1' }]);
    const { result } = renderHook(() => useTRD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listTRD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTRD(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session no fetch', () => {
    renderHook(() => useTRD(null));
    expect(api.listTRD).not.toHaveBeenCalled();
  });
});

describe('useSerie', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api.getSerie.mockResolvedValue({ id: 's1' });
    const { result } = renderHook(() => useSerie(S, 's1'));
    await waitFor(() => expect(result.current.data?.id).toBe('s1'));
  });
  it('disabled no fetch', () => {
    renderHook(() => useSerie(S, 's1', { enabled: false }));
    expect(api.getSerie).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getSerie.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useSerie(S, 's1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useTRDVersionActual + useVersionesTRD', () => {
  beforeEach(() => vi.clearAllMocks());
  it('versión actual', async () => {
    api.getTRDVersionActual.mockResolvedValue({ numero: 3 });
    const { result } = renderHook(() => useTRDVersionActual(S));
    await waitFor(() => expect(result.current.data?.numero).toBe(3));
  });
  it('versión actual error', async () => {
    api.getTRDVersionActual.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTRDVersionActual(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('lista versiones', async () => {
    api.listVersionesTRD.mockResolvedValue({ items: [{ id: 'v1' }] });
    const { result } = renderHook(() => useVersionesTRD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('lista versiones array', async () => {
    api.listVersionesTRD.mockResolvedValue([{ id: 'v1' }]);
    const { result } = renderHook(() => useVersionesTRD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('lista versiones disabled', () => {
    renderHook(() => useVersionesTRD(S, { enabled: false }));
    expect(api.listVersionesTRD).not.toHaveBeenCalled();
  });
  it('lista versiones error', async () => {
    api.listVersionesTRD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useVersionesTRD(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useTVD', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items', async () => {
    api.listTVD.mockResolvedValue({ items: [{ id: 't1' }], total: 1 });
    const { result } = renderHook(() => useTVD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array', async () => {
    api.listTVD.mockResolvedValue([{ id: 't1' }]);
    const { result } = renderHook(() => useTVD(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listTVD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTVD(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators TRD', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['crearSerie', useCrearSerie, 'crearSerie'],
    ['actualizarSerie', useActualizarSerie, 'actualizarSerie'],
    ['eliminarSerie', useEliminarSerie, 'eliminarSerie'],
    ['crearSubserie', useCrearSubserie, 'crearSubserie'],
    ['crearTipo', useCrearTipoDocumental, 'crearTipoDocumental'],
    ['nuevaVersionTRD', useNuevaVersionTRD, 'nuevaVersionTRD'],
    ['aprobarVersionTRD', useAprobarVersionTRD, 'aprobarVersionTRD'],
    ['actualizarTVD', useActualizarTVD, 'actualizarTVD'],
    ['clasificar', useClasificarConTRD, 'clasificarConTRD'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ id: 'r' });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ id: 'r' });
  });
  it('propaga error', async () => {
    api.crearSerie.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCrearSerie(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
