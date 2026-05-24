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
  cerrarPQRSD: vi.fn(),
  reabrirPQRSD: vi.fn(),
  trasladarPQRSD: vi.fn(),
  solicitarInfoAdicionalPQRSD: vi.fn(),
  suspenderTerminoPQRSD: vi.fn(),
  reanudarTerminoPQRSD: vi.fn(),
  listSuspensionesPQRSD: vi.fn(),
  getReportesPQRSD: vi.fn(),
  exportarReportePQRSD: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  usePQRSDDashboard, usePQRSDList, usePQRSD,
  useAsignarDependencia, useAsignarFuncionario, useReasignarPQRSD,
  useProyectarRespuesta, useEnviarARevision, useRevisarRespuesta,
  useAprobarRespuesta, useFirmarRespuesta,
  useRadicarSalidaRespuesta, useEnviarRespuesta,
  useCerrarPQRSD, useReabrirPQRSD, useTrasladarPQRSD,
  useSolicitarInfoAdicional, useSuspenderTermino, useReanudarTermino,
  useSuspensionesPQRSD, useReportesPQRSD,
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

describe('mutators UI-6 (cierre, traslado, suspensión)', () => {
  beforeEach(() => vi.clearAllMocks());

  const ui6Cases = [
    ['cerrarPQRSD', useCerrarPQRSD],
    ['reabrirPQRSD', useReabrirPQRSD],
    ['trasladarPQRSD', useTrasladarPQRSD],
    ['solicitarInfoAdicionalPQRSD', useSolicitarInfoAdicional],
    ['suspenderTerminoPQRSD', useSuspenderTermino],
    ['reanudarTerminoPQRSD', useReanudarTermino],
  ];

  it.each(ui6Cases)('%s submit OK', async (fnName, hookFn) => {
    api[fnName].mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => hookFn(S));
    await act(async () => {
      await result.current.submit('id', { justificacion: 'X' });
    });
    expect(api[fnName]).toHaveBeenCalled();
  });

  it.each(ui6Cases)('%s submit error rethrows', async (fnName, hookFn) => {
    api[fnName].mockRejectedValueOnce(new Error('e'));
    const { result } = renderHook(() => hookFn(S));
    await act(async () => {
      await expect(result.current.submit('id', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useSuspensionesPQRSD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('carga lista normal', async () => {
    api.listSuspensionesPQRSD.mockResolvedValue({
      items: [{ id: 's1', fecha_inicio: '2026-05-23' }],
    });
    const { result } = renderHook(() => useSuspensionesPQRSD(S, 'p1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });

  it('items raw array', async () => {
    api.listSuspensionesPQRSD.mockResolvedValue([{ id: 's1' }]);
    const { result } = renderHook(() => useSuspensionesPQRSD(S, 'p1'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });

  it('disabled NO fetch', () => {
    renderHook(() => useSuspensionesPQRSD(S, 'p1', { enabled: false }));
    expect(api.listSuspensionesPQRSD).not.toHaveBeenCalled();
  });

  it('error', async () => {
    api.listSuspensionesPQRSD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useSuspensionesPQRSD(S, 'p1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useReportesPQRSD', () => {
  beforeEach(() => vi.clearAllMocks());

  it('carga data + exportar OK', async () => {
    api.getReportesPQRSD.mockResolvedValue({ totales: { total: 9 } });
    api.exportarReportePQRSD.mockResolvedValue({ export_id: 'e1' });
    const { result } = renderHook(() => useReportesPQRSD(S, {}));
    await waitFor(() => expect(result.current.data.totales.total).toBe(9));
    const r = await act(() => result.current.exportar('xlsx'));
    expect(r.export_id).toBe('e1');
  });

  it('error', async () => {
    api.getReportesPQRSD.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useReportesPQRSD(S, {}));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });

  it('sin session NO fetch', () => {
    renderHook(() => useReportesPQRSD(null, {}));
    expect(api.getReportesPQRSD).not.toHaveBeenCalled();
  });
});
