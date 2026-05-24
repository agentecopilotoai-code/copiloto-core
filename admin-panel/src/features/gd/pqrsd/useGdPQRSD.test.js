import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listPQRSDFiltrados: vi.fn(),
  getPQRSDDashboard: vi.fn(),
  getPQRSD: vi.fn(),
  asignarDependenciaPQRSD: vi.fn(),
  asignarFuncionarioPQRSD: vi.fn(),
  reasignarPQRSD: vi.fn(),
  proyectarRespuestaPQRSD: vi.fn(),
  enviarRespuestaARevision: vi.fn(),
  revisarRespuestaPQRSD: vi.fn(),
  aprobarRespuestaPQRSD: vi.fn(),
  firmarRespuestaPQRSD: vi.fn(),
  radicarSalidaRespuesta: vi.fn(),
  enviarRespuestaPQRSD: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  usePQRSDDashboard, usePQRSDList, usePQRSD,
  useAsignarDependencia, useAsignarFuncionario, useReasignarPQRSD,
  useProyectarRespuesta, useEnviarARevision, useRevisarRespuesta,
  useAprobarRespuesta, useFirmarRespuesta,
  useRadicarSalidaRespuesta, useEnviarRespuesta,
} from './useGdPQRSD.js';

const S = { token: 't' };

describe('usePQRSDDashboard', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga data', async () => {
    api.getPQRSDDashboard.mockResolvedValue({ totales: { total: 42 } });
    const { result } = renderHook(() => usePQRSDDashboard(S, {}));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.totales.total).toBe(42);
  });
  it('error', async () => {
    api.getPQRSDDashboard.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePQRSDDashboard(S, {}));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session NO fetch', () => {
    renderHook(() => usePQRSDDashboard(null));
    expect(api.getPQRSDDashboard).not.toHaveBeenCalled();
  });
});

describe('usePQRSDList', () => {
  beforeEach(() => vi.clearAllMocks());
  it('lista normal', async () => {
    api.listPQRSDFiltrados.mockResolvedValue({ items: [{ id: 'p1' }], total: 1 });
    const { result } = renderHook(() => usePQRSDList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('items raw array', async () => {
    api.listPQRSDFiltrados.mockResolvedValue([{ id: 'p1' }]);
    const { result } = renderHook(() => usePQRSDList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listPQRSDFiltrados.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePQRSDList(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session NO fetch', () => {
    renderHook(() => usePQRSDList(null));
    expect(api.listPQRSDFiltrados).not.toHaveBeenCalled();
  });
});

describe('usePQRSD', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga ficha', async () => {
    api.getPQRSD.mockResolvedValue({ id: 'p1', numero_radicado: 'X' });
    const { result } = renderHook(() => usePQRSD(S, 'p1'));
    await waitFor(() => expect(result.current.data.id).toBe('p1'));
  });
  it('disabled NO fetch', () => {
    renderHook(() => usePQRSD(S, 'p1', { enabled: false }));
    expect(api.getPQRSD).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getPQRSD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePQRSD(S, 'p1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators (8)', () => {
  beforeEach(() => vi.clearAllMocks());

  const cases = [
    ['asignarDependenciaPQRSD', useAsignarDependencia],
    ['asignarFuncionarioPQRSD', useAsignarFuncionario],
    ['reasignarPQRSD', useReasignarPQRSD],
    ['proyectarRespuestaPQRSD', useProyectarRespuesta],
    ['enviarRespuestaARevision', useEnviarARevision],
    ['revisarRespuestaPQRSD', useRevisarRespuesta],
    ['aprobarRespuestaPQRSD', useAprobarRespuesta],
    ['firmarRespuestaPQRSD', useFirmarRespuesta],
    ['radicarSalidaRespuesta', useRadicarSalidaRespuesta],
    ['enviarRespuestaPQRSD', useEnviarRespuesta],
  ];

  it.each(cases)('%s submit OK', async (fnName, hookFn) => {
    api[fnName].mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => hookFn(S));
    await act(async () => {
      const r = await result.current.submit('id', {});
      expect(r.ok).toBe(true);
    });
    expect(api[fnName]).toHaveBeenCalled();
  });

  it.each(cases)('%s submit error rethrows', async (fnName, hookFn) => {
    api[fnName].mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => hookFn(S));
    await act(async () => {
      await expect(result.current.submit('id', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
