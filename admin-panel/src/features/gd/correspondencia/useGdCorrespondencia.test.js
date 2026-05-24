import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  crearCorrespondenciaInterna: vi.fn(),
  listCorrespondencia: vi.fn(),
  getCorrespondencia: vi.fn(),
  marcarLeidaCorrespondencia: vi.fn(),
  responderCorrespondencia: vi.fn(),
  reenviarCorrespondencia: vi.fn(),
  crearBorradorCorrespondenciaExterna: vi.fn(),
  enviarCorrespondenciaARevision: vi.fn(),
  revisarCorrespondencia: vi.fn(),
  aprobarCorrespondencia: vi.fn(),
  firmarCorrespondencia: vi.fn(),
  radicarSalidaCorrespondencia: vi.fn(),
  enviarCorrespondencia: vi.fn(),
  registrarSoporteEnvio: vi.fn(),
  agregarDestinatarioCorrespondencia: vi.fn(),
  quitarDestinatarioCorrespondencia: vi.fn(),
  solicitarAnulacionCorrespondencia: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useCorrespondenciaList, useCorrespondencia,
  useCrearCorrespondenciaInterna,
  useCrearBorradorCorrespondenciaExterna,
  useMarcarLeida, useResponderCorrespondencia, useReenviarCorrespondencia,
  useEnviarCERevision, useRevisarCorrespondencia,
  useAprobarCorrespondencia, useFirmarCorrespondencia,
  useRadicarSalidaCorrespondencia, useEnviarCorrespondencia,
  useRegistrarSoporteEnvio,
  useAgregarDestinatario, useQuitarDestinatario,
  useSolicitarAnulacionCorrespondencia,
} from './useGdCorrespondencia.js';

const S = { token: 't' };

describe('useCorrespondenciaList', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga items + total', async () => {
    api.listCorrespondencia.mockResolvedValue({ items: [{ id: 'c1' }], total: 1 });
    const { result } = renderHook(() => useCorrespondenciaList(S));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });
  it('items raw array', async () => {
    api.listCorrespondencia.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useCorrespondenciaList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listCorrespondencia.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorrespondenciaList(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session NO fetch', () => {
    renderHook(() => useCorrespondenciaList(null));
    expect(api.listCorrespondencia).not.toHaveBeenCalled();
  });
});

describe('useCorrespondencia (ficha)', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga ficha', async () => {
    api.getCorrespondencia.mockResolvedValue({ id: 'c1', asunto: 'X' });
    const { result } = renderHook(() => useCorrespondencia(S, 'c1'));
    await waitFor(() => expect(result.current.data.id).toBe('c1'));
  });
  it('disabled NO fetch', () => {
    renderHook(() => useCorrespondencia(S, 'c1', { enabled: false }));
    expect(api.getCorrespondencia).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getCorrespondencia.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorrespondencia(S, 'c1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators (15)', () => {
  beforeEach(() => vi.clearAllMocks());

  const cases = [
    ['crearCorrespondenciaInterna', useCrearCorrespondenciaInterna],
    ['crearBorradorCorrespondenciaExterna', useCrearBorradorCorrespondenciaExterna],
    ['marcarLeidaCorrespondencia', useMarcarLeida],
    ['responderCorrespondencia', useResponderCorrespondencia],
    ['reenviarCorrespondencia', useReenviarCorrespondencia],
    ['enviarCorrespondenciaARevision', useEnviarCERevision],
    ['revisarCorrespondencia', useRevisarCorrespondencia],
    ['aprobarCorrespondencia', useAprobarCorrespondencia],
    ['firmarCorrespondencia', useFirmarCorrespondencia],
    ['radicarSalidaCorrespondencia', useRadicarSalidaCorrespondencia],
    ['enviarCorrespondencia', useEnviarCorrespondencia],
    ['registrarSoporteEnvio', useRegistrarSoporteEnvio],
    ['agregarDestinatarioCorrespondencia', useAgregarDestinatario],
    ['quitarDestinatarioCorrespondencia', useQuitarDestinatario],
    ['solicitarAnulacionCorrespondencia', useSolicitarAnulacionCorrespondencia],
  ];

  it.each(cases)('%s submit OK', async (fnName, hookFn) => {
    api[fnName].mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => hookFn(S));
    await act(async () => { await result.current.submit('id', {}); });
    expect(api[fnName]).toHaveBeenCalled();
  });

  it.each(cases)('%s submit error rethrows', async (fnName, hookFn) => {
    api[fnName].mockRejectedValueOnce(new Error('e'));
    const { result } = renderHook(() => hookFn(S));
    await act(async () => {
      await expect(result.current.submit('id', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
