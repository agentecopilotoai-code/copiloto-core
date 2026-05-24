import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listPorFirmar: vi.fn(),
  getEvidenciaFirma: vi.fn(),
  registrarFirmaEscaneada: vi.fn(),
  firmarDocumento: vi.fn(),
  rechazarFirmaDocumento: vi.fn(),
  listFirmantesAutorizados: vi.fn(),
  crearFirmanteAutorizado: vi.fn(),
  actualizarFirmanteAutorizado: vi.fn(),
  inactivarFirmanteAutorizado: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  usePorFirmar, useEvidenciaFirma, useFirmantesAutorizados,
  useRegistrarFirmaEscaneada, useFirmarDocumento, useRechazarFirmaDocumento,
  useCrearFirmanteAutorizado, useActualizarFirmanteAutorizado,
  useInactivarFirmanteAutorizado,
} from './useGdFirmas.js';

const S = { token: 't' };

describe('usePorFirmar', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items + total', async () => {
    api.listPorFirmar.mockResolvedValue({ items: [{ id: 'f1' }], total: 1 });
    const { result } = renderHook(() => usePorFirmar(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array directo', async () => {
    api.listPorFirmar.mockResolvedValue([{ id: 'f1' }]);
    const { result } = renderHook(() => usePorFirmar(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listPorFirmar.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePorFirmar(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session no fetch', () => {
    renderHook(() => usePorFirmar(null));
    expect(api.listPorFirmar).not.toHaveBeenCalled();
  });
});

describe('useEvidenciaFirma', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga evidencia', async () => {
    api.getEvidenciaFirma.mockResolvedValue({ hash_documento: 'abc' });
    const { result } = renderHook(() => useEvidenciaFirma(S, 'f1'));
    await waitFor(() => expect(result.current.data?.hash_documento).toBe('abc'));
  });
  it('disabled no fetch', () => {
    renderHook(() => useEvidenciaFirma(S, 'f1', { enabled: false }));
    expect(api.getEvidenciaFirma).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getEvidenciaFirma.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useEvidenciaFirma(S, 'f1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useFirmantesAutorizados', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api.listFirmantesAutorizados.mockResolvedValue({ items: [{ id: 'a1' }] });
    const { result } = renderHook(() => useFirmantesAutorizados(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array directo', async () => {
    api.listFirmantesAutorizados.mockResolvedValue([{ id: 'a1' }]);
    const { result } = renderHook(() => useFirmantesAutorizados(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('disabled no fetch', () => {
    renderHook(() => useFirmantesAutorizados(S, { enabled: false }));
    expect(api.listFirmantesAutorizados).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.listFirmantesAutorizados.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useFirmantesAutorizados(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators firmas', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['escaneada', useRegistrarFirmaEscaneada, 'registrarFirmaEscaneada'],
    ['firmar', useFirmarDocumento, 'firmarDocumento'],
    ['rechazar', useRechazarFirmaDocumento, 'rechazarFirmaDocumento'],
    ['crearFirmante', useCrearFirmanteAutorizado, 'crearFirmanteAutorizado'],
    ['actFirmante', useActualizarFirmanteAutorizado, 'actualizarFirmanteAutorizado'],
    ['inactFirmante', useInactivarFirmanteAutorizado, 'inactivarFirmanteAutorizado'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ id: 'r' });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ id: 'r' });
  });
  it('propaga error', async () => {
    api.firmarDocumento.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useFirmarDocumento(S));
    await act(async () => {
      await expect(result.current.submit('d1')).rejects.toThrow('boom');
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
