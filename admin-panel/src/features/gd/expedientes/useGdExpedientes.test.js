import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listExpedientes: vi.fn(),
  getExpediente: vi.fn(),
  crearExpediente: vi.fn(),
  actualizarExpediente: vi.fn(),
  listDocumentosExpediente: vi.fn(),
  agregarDocumentoExpediente: vi.fn(),
  quitarDocumentoExpediente: vi.fn(),
  cerrarExpediente: vi.fn(),
  transferirExpediente: vi.fn(),
  reabrirExpediente: vi.fn(),
  getIndiceExpediente: vi.fn(),
  getActaCierreExpediente: vi.fn(),
  buscarExpedientes: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useExpedientesList, useExpediente, useDocumentosExpediente,
  useIndiceExpediente, useActaCierreExpediente, useBuscarExpedientes,
  useCrearExpediente, useActualizarExpediente,
  useAgregarDocumentoExp, useQuitarDocumentoExp,
  useCerrarExpediente, useTransferirExpediente, useReabrirExpediente,
} from './useGdExpedientes.js';

const S = { token: 't' };

describe('useExpedientesList', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items+total', async () => {
    api.listExpedientes.mockResolvedValue({ items: [{ id: 'e1' }], total: 1 });
    const { result } = renderHook(() => useExpedientesList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array', async () => {
    api.listExpedientes.mockResolvedValue([{ id: 'e1' }]);
    const { result } = renderHook(() => useExpedientesList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listExpedientes.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useExpedientesList(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useExpedientesList(null));
    expect(api.listExpedientes).not.toHaveBeenCalled();
  });
});

describe.each([
  ['useExpediente', useExpediente, 'getExpediente'],
  ['useIndiceExpediente', useIndiceExpediente, 'getIndiceExpediente'],
  ['useActaCierreExpediente', useActaCierreExpediente, 'getActaCierreExpediente'],
])('%s', (_n, hook, apiName) => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api[apiName].mockResolvedValue({ id: 'x' });
    const { result } = renderHook(() => hook(S, 'e1'));
    await waitFor(() => expect(result.current.data).toBeTruthy());
  });
  it('disabled no fetch', () => {
    renderHook(() => hook(S, 'e1', { enabled: false }));
    expect(api[apiName]).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api[apiName].mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => hook(S, 'e1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useDocumentosExpediente', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items', async () => {
    api.listDocumentosExpediente.mockResolvedValue({ items: [{ id: 'd1' }] });
    const { result } = renderHook(() => useDocumentosExpediente(S, 'e1'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array', async () => {
    api.listDocumentosExpediente.mockResolvedValue([{ id: 'd1' }]);
    const { result } = renderHook(() => useDocumentosExpediente(S, 'e1'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('disabled no fetch', () => {
    renderHook(() => useDocumentosExpediente(S, 'e1', { enabled: false }));
    expect(api.listDocumentosExpediente).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.listDocumentosExpediente.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useDocumentosExpediente(S, 'e1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useBuscarExpedientes', () => {
  beforeEach(() => vi.clearAllMocks());
  it('busca + setea ran', async () => {
    api.buscarExpedientes.mockResolvedValue({ items: [{ id: 'x' }], total: 1 });
    const { result } = renderHook(() => useBuscarExpedientes(S));
    expect(result.current.ran).toBe(false);
    await act(async () => { await result.current.buscar({ q: 'a' }); });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.ran).toBe(true);
  });
  it('busca array directo', async () => {
    api.buscarExpedientes.mockResolvedValue([{ id: 'x' }]);
    const { result } = renderHook(() => useBuscarExpedientes(S));
    await act(async () => { await result.current.buscar({}); });
    expect(result.current.items).toHaveLength(1);
  });
  it('busca error', async () => {
    api.buscarExpedientes.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useBuscarExpedientes(S));
    await act(async () => { await result.current.buscar({}); });
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.ran).toBe(true);
  });
  it('busca sin session no-op', async () => {
    const { result } = renderHook(() => useBuscarExpedientes(null));
    await act(async () => { await result.current.buscar({}); });
    expect(api.buscarExpedientes).not.toHaveBeenCalled();
  });
});

describe('mutators expedientes', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['crear', useCrearExpediente, 'crearExpediente'],
    ['actualizar', useActualizarExpediente, 'actualizarExpediente'],
    ['agregarDoc', useAgregarDocumentoExp, 'agregarDocumentoExpediente'],
    ['quitarDoc', useQuitarDocumentoExp, 'quitarDocumentoExpediente'],
    ['cerrar', useCerrarExpediente, 'cerrarExpediente'],
    ['transferir', useTransferirExpediente, 'transferirExpediente'],
    ['reabrir', useReabrirExpediente, 'reabrirExpediente'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ id: 'r' });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ id: 'r' });
  });
  it('propaga error', async () => {
    api.cerrarExpediente.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCerrarExpediente(S));
    await act(async () => {
      await expect(result.current.submit('e1', {})).rejects.toThrow('boom');
    });
  });
});
