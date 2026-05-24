import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  buscarAuditoria: vi.fn(),
  getEventoAuditoria: vi.fn(),
  exportarAuditoria: vi.fn(),
  listCatalogoEntidadesAuditoria: vi.fn(),
  listCatalogoAccionesAuditoria: vi.fn(),
  getReportesConsolidados: vi.fn(),
  exportarReporteConsolidado: vi.fn(),
  exportarReporteEjecutivoPdf: vi.fn(),
  getResumenIntegridadAuditor: vi.fn(),
  verificarHashRegistro: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useAuditoriaBandeja, useEventoAuditoria, useCatalogosAuditoria,
  useReportesConsolidados, useResumenIntegridadAuditor,
  useExportarAuditoria, useExportarReporteConsolidado,
  useExportarReporteEjecutivoPdf, useVerificarHashRegistro,
} from './useGdAuditoria.js';

const S = { token: 't' };

describe('useAuditoriaBandeja', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items+total', async () => {
    api.buscarAuditoria.mockResolvedValue({ items: [{ id: 'e1' }], total: 1 });
    const { result } = renderHook(() => useAuditoriaBandeja(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array', async () => {
    api.buscarAuditoria.mockResolvedValue([{ id: 'e1' }]);
    const { result } = renderHook(() => useAuditoriaBandeja(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.buscarAuditoria.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAuditoriaBandeja(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useAuditoriaBandeja(null));
    expect(api.buscarAuditoria).not.toHaveBeenCalled();
  });
});

describe('useEventoAuditoria', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api.getEventoAuditoria.mockResolvedValue({ id: 'e1' });
    const { result } = renderHook(() => useEventoAuditoria(S, 'e1'));
    await waitFor(() => expect(result.current.data?.id).toBe('e1'));
  });
  it('disabled', () => {
    renderHook(() => useEventoAuditoria(S, 'e1', { enabled: false }));
    expect(api.getEventoAuditoria).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getEventoAuditoria.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useEventoAuditoria(S, 'e1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useCatalogosAuditoria', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga entidades + acciones (en paralelo)', async () => {
    api.listCatalogoEntidadesAuditoria.mockResolvedValue([{ codigo: 'pqrsd' }]);
    api.listCatalogoAccionesAuditoria.mockResolvedValue([{ codigo: 'crear' }]);
    const { result } = renderHook(() => useCatalogosAuditoria(S));
    await waitFor(() => expect(result.current.entidades).toHaveLength(1));
    expect(result.current.acciones).toHaveLength(1);
  });
  it('entidades formato items', async () => {
    api.listCatalogoEntidadesAuditoria.mockResolvedValue({ items: [{ codigo: 'doc' }] });
    api.listCatalogoAccionesAuditoria.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useCatalogosAuditoria(S));
    await waitFor(() => expect(result.current.entidades).toHaveLength(1));
  });
  it('error', async () => {
    api.listCatalogoEntidadesAuditoria.mockRejectedValue(new Error('e'));
    api.listCatalogoAccionesAuditoria.mockResolvedValue([]);
    const { result } = renderHook(() => useCatalogosAuditoria(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useCatalogosAuditoria(null));
    expect(api.listCatalogoEntidadesAuditoria).not.toHaveBeenCalled();
  });
});

describe('useReportesConsolidados + useResumenIntegridadAuditor', () => {
  beforeEach(() => vi.clearAllMocks());
  it('reportes carga', async () => {
    api.getReportesConsolidados.mockResolvedValue({ pqrsd_total: 100 });
    const { result } = renderHook(() => useReportesConsolidados(S));
    await waitFor(() => expect(result.current.data?.pqrsd_total).toBe(100));
  });
  it('reportes error', async () => {
    api.getReportesConsolidados.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useReportesConsolidados(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('reportes sin session', () => {
    renderHook(() => useReportesConsolidados(null));
    expect(api.getReportesConsolidados).not.toHaveBeenCalled();
  });
  it('integridad carga', async () => {
    api.getResumenIntegridadAuditor.mockResolvedValue({ hash_raiz: 'abc' });
    const { result } = renderHook(() => useResumenIntegridadAuditor(S));
    await waitFor(() => expect(result.current.data?.hash_raiz).toBe('abc'));
  });
  it('integridad error', async () => {
    api.getResumenIntegridadAuditor.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useResumenIntegridadAuditor(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators auditoría', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['exportarAud', useExportarAuditoria, 'exportarAuditoria'],
    ['exportarRep', useExportarReporteConsolidado, 'exportarReporteConsolidado'],
    ['exportarPDF', useExportarReporteEjecutivoPdf, 'exportarReporteEjecutivoPdf'],
    ['verifHash', useVerificarHashRegistro, 'verificarHashRegistro'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ ok: true });
  });
  it('propaga error', async () => {
    api.exportarAuditoria.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useExportarAuditoria(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
  });
});
