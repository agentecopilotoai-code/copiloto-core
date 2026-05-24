import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listDocumentos: vi.fn(),
  getDocumento: vi.fn(),
  listVersionesDocumento: vi.fn(),
  crearDocumento: vi.fn(),
  nuevaVersionDocumento: vi.fn(),
  anularDocumento: vi.fn(),
  subirArchivo: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useDocumentosList, useDocumento, useVersionesDocumento,
  useCrearDocumento, useNuevaVersionDocumento, useAnularDocumento,
  useSubirArchivo,
} from './useGdDocumentos.js';

const S = { token: 't' };

describe('useDocumentosList', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga items + total', async () => {
    api.listDocumentos.mockResolvedValue({ items: [{ id: 'd1' }], total: 1 });
    const { result } = renderHook(() => useDocumentosList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.total).toBe(1);
  });
  it('items array directo', async () => {
    api.listDocumentos.mockResolvedValue([{ id: 'd1' }]);
    const { result } = renderHook(() => useDocumentosList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listDocumentos.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useDocumentosList(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session no fetch', () => {
    renderHook(() => useDocumentosList(null));
    expect(api.listDocumentos).not.toHaveBeenCalled();
  });
});

describe('useDocumento', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga ficha', async () => {
    api.getDocumento.mockResolvedValue({ id: 'd1' });
    const { result } = renderHook(() => useDocumento(S, 'd1'));
    await waitFor(() => expect(result.current.data?.id).toBe('d1'));
  });
  it('disabled NO fetch', () => {
    renderHook(() => useDocumento(S, 'd1', { enabled: false }));
    expect(api.getDocumento).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getDocumento.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useDocumento(S, 'd1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useVersionesDocumento', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga versiones', async () => {
    api.listVersionesDocumento.mockResolvedValue({ items: [{ id: 'v1' }] });
    const { result } = renderHook(() => useVersionesDocumento(S, 'd1'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array raw', async () => {
    api.listVersionesDocumento.mockResolvedValue([{ id: 'v1' }]);
    const { result } = renderHook(() => useVersionesDocumento(S, 'd1'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('disabled no fetch', () => {
    renderHook(() => useVersionesDocumento(S, 'd1', { enabled: false }));
    expect(api.listVersionesDocumento).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.listVersionesDocumento.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useVersionesDocumento(S, 'd1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['useCrearDocumento', useCrearDocumento, 'crearDocumento'],
    ['useNuevaVersionDocumento', useNuevaVersionDocumento, 'nuevaVersionDocumento'],
    ['useAnularDocumento', useAnularDocumento, 'anularDocumento'],
    ['useSubirArchivo', useSubirArchivo, 'subirArchivo'],
  ])('%s submit OK', async (_n, hook, apiName) => {
    api[apiName].mockResolvedValue({ id: 'x' });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('p'); });
    expect(r).toEqual({ id: 'x' });
    expect(api[apiName]).toHaveBeenCalled();
  });
  it('mutator propaga error', async () => {
    api.crearDocumento.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCrearDocumento(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
