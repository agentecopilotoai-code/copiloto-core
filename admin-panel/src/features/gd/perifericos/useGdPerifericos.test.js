import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listPerifericos: vi.fn(),
  getPeriferico: vi.fn(),
  crearPeriferico: vi.fn(),
  actualizarPeriferico: vi.fn(),
  inactivarPeriferico: vi.fn(),
  getEstadoPerifericos: vi.fn(),
  imprimirEtiqueta: vi.fn(),
  imprimirConstancia: vi.fn(),
  reimprimir: vi.fn(),
  listTrabajosImpresion: vi.fn(),
  digitalizarIndividual: vi.fn(),
  digitalizarLote: vi.fn(),
  listColaDigitalizacion: vi.fn(),
  asociarDigitalizacionARadicado: vi.fn(),
  reemplazarDigitalizacion: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  usePerifericos, usePeriferico, useEstadoPerifericos,
  useTrabajosImpresion, useColaDigitalizacion,
  useCrearPeriferico, useActualizarPeriferico, useInactivarPeriferico,
  useImprimirEtiqueta, useImprimirConstancia, useReimprimir,
  useDigitalizarIndividual, useDigitalizarLote,
  useAsociarDigitalizacionARadicado, useReemplazarDigitalizacion,
} from './useGdPerifericos.js';

const S = { token: 't' };

describe('readers periféricos', () => {
  beforeEach(() => vi.clearAllMocks());
  it('usePerifericos items+total', async () => {
    api.listPerifericos.mockResolvedValue({ items: [{ id: 'p1' }], total: 1 });
    const { result } = renderHook(() => usePerifericos(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('usePerifericos array', async () => {
    api.listPerifericos.mockResolvedValue([{ id: 'p1' }]);
    const { result } = renderHook(() => usePerifericos(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('usePerifericos error', async () => {
    api.listPerifericos.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePerifericos(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('usePerifericos sin session', () => {
    renderHook(() => usePerifericos(null));
    expect(api.listPerifericos).not.toHaveBeenCalled();
  });
  it('usePeriferico carga', async () => {
    api.getPeriferico.mockResolvedValue({ id: 'p1' });
    const { result } = renderHook(() => usePeriferico(S, 'p1'));
    await waitFor(() => expect(result.current.data?.id).toBe('p1'));
  });
  it('usePeriferico disabled', () => {
    renderHook(() => usePeriferico(S, 'p1', { enabled: false }));
    expect(api.getPeriferico).not.toHaveBeenCalled();
  });
  it('usePeriferico error', async () => {
    api.getPeriferico.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePeriferico(S, 'p1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useEstadoPerifericos carga', async () => {
    api.getEstadoPerifericos.mockResolvedValue({ en_linea: 5 });
    const { result } = renderHook(() => useEstadoPerifericos(S));
    await waitFor(() => expect(result.current.data?.en_linea).toBe(5));
  });
  it('useEstadoPerifericos error', async () => {
    api.getEstadoPerifericos.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useEstadoPerifericos(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useTrabajosImpresion items', async () => {
    api.listTrabajosImpresion.mockResolvedValue({ items: [{ id: 't1' }] });
    const { result } = renderHook(() => useTrabajosImpresion(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useTrabajosImpresion array', async () => {
    api.listTrabajosImpresion.mockResolvedValue([{ id: 't1' }]);
    const { result } = renderHook(() => useTrabajosImpresion(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useTrabajosImpresion error', async () => {
    api.listTrabajosImpresion.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTrabajosImpresion(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useColaDigitalizacion items', async () => {
    api.listColaDigitalizacion.mockResolvedValue({ items: [{ id: 'd1' }] });
    const { result } = renderHook(() => useColaDigitalizacion(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useColaDigitalizacion error', async () => {
    api.listColaDigitalizacion.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useColaDigitalizacion(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators periféricos', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['crear', useCrearPeriferico, 'crearPeriferico'],
    ['actualizar', useActualizarPeriferico, 'actualizarPeriferico'],
    ['inactivar', useInactivarPeriferico, 'inactivarPeriferico'],
    ['eti', useImprimirEtiqueta, 'imprimirEtiqueta'],
    ['cons', useImprimirConstancia, 'imprimirConstancia'],
    ['reimp', useReimprimir, 'reimprimir'],
    ['digInd', useDigitalizarIndividual, 'digitalizarIndividual'],
    ['digLote', useDigitalizarLote, 'digitalizarLote'],
    ['asoc', useAsociarDigitalizacionARadicado, 'asociarDigitalizacionARadicado'],
    ['reemp', useReemplazarDigitalizacion, 'reemplazarDigitalizacion'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ ok: true });
  });
  it('propaga error', async () => {
    api.crearPeriferico.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCrearPeriferico(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
  });
});
