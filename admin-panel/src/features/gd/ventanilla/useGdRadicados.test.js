import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  crearRadicadoEntrada: vi.fn(),
  crearRadicadoSalida: vi.fn(),
  clasificarRadicado: vi.fn(),
  listColaPendientesClasificacion: vi.fn(),
  getRadicado: vi.fn(),
  reclasificarRadicado: vi.fn(),
  corregirDatosMenores: vi.fn(),
  solicitarAnulacionRadicado: vi.fn(),
  listAnulacionesPendientes: vi.fn(),
  aprobarAnulacion: vi.fn(),
  rechazarAnulacion: vi.fn(),
  buscarRadicados: vi.fn(),
  getReportesVentanilla: vi.fn(),
  exportarReporteVentanilla: vi.fn(),
}));

import {
  crearRadicadoEntrada,
  crearRadicadoSalida,
  clasificarRadicado,
  listColaPendientesClasificacion,
  getRadicado,
  reclasificarRadicado,
  corregirDatosMenores,
  solicitarAnulacionRadicado,
  listAnulacionesPendientes,
  aprobarAnulacion,
  rechazarAnulacion,
  buscarRadicados,
  getReportesVentanilla,
  exportarReporteVentanilla,
} from '../services/gdApi.js';

import {
  useCrearRadicadoEntrada,
  useCrearRadicadoSalida,
  useColaPendientesClasificacion,
  useClasificarRadicado,
  useGdRadicado,
  useReclasificarRadicado,
  useCorregirDatosMenores,
  useSolicitarAnulacion,
  useAnulacionesPendientes,
  useBuscarRadicados,
  useReportesVentanilla,
} from './useGdRadicados.js';

const SESSION = { token: 't' };

describe('useCrearRadicadoEntrada', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('submit success → guarda radicado en state', async () => {
    crearRadicadoEntrada.mockResolvedValueOnce({ id: 'r1', numero_radicado: '2026-E-1' });
    const { result } = renderHook(() => useCrearRadicadoEntrada(SESSION));
    await act(async () => {
      await result.current.submit({ asunto: 'X' });
    });
    expect(result.current.radicado.id).toBe('r1');
    expect(result.current.error).toBeNull();
  });

  it('submit error → guarda error y rethrows', async () => {
    const err = new Error('boom');
    crearRadicadoEntrada.mockRejectedValueOnce(err);
    const { result } = renderHook(() => useCrearRadicadoEntrada(SESSION));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toBe(err);
    });
    expect(result.current.error).toBe(err);
    expect(result.current.radicado).toBeNull();
  });

  it('reset limpia state', async () => {
    crearRadicadoEntrada.mockResolvedValueOnce({ id: 'r1' });
    const { result } = renderHook(() => useCrearRadicadoEntrada(SESSION));
    await act(async () => { await result.current.submit({}); });
    act(() => result.current.reset());
    expect(result.current.radicado).toBeNull();
  });
});

describe('useCrearRadicadoSalida', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('submit OK', async () => {
    crearRadicadoSalida.mockResolvedValueOnce({ id: 's1' });
    const { result } = renderHook(() => useCrearRadicadoSalida(SESSION));
    await act(async () => {
      const r = await result.current.submit({});
      expect(r.id).toBe('s1');
    });
  });

  it('submit error', async () => {
    crearRadicadoSalida.mockRejectedValueOnce(new Error('x'));
    const { result } = renderHook(() => useCrearRadicadoSalida(SESSION));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useColaPendientesClasificacion', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('fetch inicial y filtros', async () => {
    listColaPendientesClasificacion.mockResolvedValue({
      items: [{ id: 'r1', numero_radicado: '2026-E-1' }],
      total: 1,
    });
    const { result } = renderHook(() =>
      useColaPendientesClasificacion(SESSION, { canal_id: 'web' }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('items=array (sin envoltorio) también funciona', async () => {
    listColaPendientesClasificacion.mockResolvedValue([{ id: 'a' }]);
    const { result } = renderHook(() => useColaPendientesClasificacion(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });

  it('error', async () => {
    listColaPendientesClasificacion.mockRejectedValue(new Error('net'));
    const { result } = renderHook(() => useColaPendientesClasificacion(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.items).toEqual([]);
  });

  it('refresh redispara fetch', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useColaPendientesClasificacion(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.refresh());
    expect(listColaPendientesClasificacion).toHaveBeenCalledTimes(2);
  });

  it('sin session no fetch', () => {
    renderHook(() => useColaPendientesClasificacion(null));
    expect(listColaPendientesClasificacion).not.toHaveBeenCalled();
  });
});

describe('useClasificarRadicado', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('submit pasa id y body', async () => {
    clasificarRadicado.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useClasificarRadicado(SESSION));
    await act(async () => {
      await result.current.submit('r1', { tipo_clasificacion: 'pqrsd' });
    });
    expect(clasificarRadicado).toHaveBeenCalledWith(SESSION, 'r1', { tipo_clasificacion: 'pqrsd' });
  });

  it('error captura', async () => {
    clasificarRadicado.mockRejectedValueOnce(new Error('fail'));
    const { result } = renderHook(() => useClasificarRadicado(SESSION));
    await act(async () => {
      await expect(result.current.submit('r1', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('hooks ventanilla parte 2 (UI-3)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('useGdRadicado carga data por id', async () => {
    getRadicado.mockResolvedValueOnce({ id: 'r1', numero_radicado: 'X' });
    const { result } = renderHook(() => useGdRadicado(SESSION, 'r1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.id).toBe('r1');
  });

  it('useGdRadicado disabled NO fetch', async () => {
    renderHook(() => useGdRadicado(SESSION, 'r1', { enabled: false }));
    expect(getRadicado).not.toHaveBeenCalled();
  });

  it('useGdRadicado error', async () => {
    getRadicado.mockRejectedValueOnce(new Error('404'));
    const { result } = renderHook(() => useGdRadicado(SESSION, 'r1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('useReclasificarRadicado submit OK + error', async () => {
    reclasificarRadicado.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useReclasificarRadicado(SESSION));
    await act(async () => {
      await result.current.submit('r1', { tipo_clasificacion: 't' });
    });
    expect(reclasificarRadicado).toHaveBeenCalled();

    reclasificarRadicado.mockRejectedValueOnce(new Error('x'));
    await act(async () => {
      await expect(result.current.submit('r1', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('useCorregirDatosMenores submit OK + error', async () => {
    corregirDatosMenores.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useCorregirDatosMenores(SESSION));
    await act(async () => {
      await result.current.submit('r1', { asunto: 'X', justificacion: 'corrijo' });
    });
    expect(corregirDatosMenores).toHaveBeenCalled();

    corregirDatosMenores.mockRejectedValueOnce(new Error('x'));
    await act(async () => {
      await expect(result.current.submit('r1', {})).rejects.toBeTruthy();
    });
  });

  it('useSolicitarAnulacion submit OK + error', async () => {
    solicitarAnulacionRadicado.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useSolicitarAnulacion(SESSION));
    await act(async () => { await result.current.submit('r1', 'motivo'); });
    expect(solicitarAnulacionRadicado).toHaveBeenCalledWith(SESSION, 'r1', 'motivo');

    solicitarAnulacionRadicado.mockRejectedValueOnce(new Error('x'));
    await act(async () => {
      await expect(result.current.submit('r1', 'm')).rejects.toBeTruthy();
    });
  });

  it('useAnulacionesPendientes carga + aprobar + rechazar', async () => {
    listAnulacionesPendientes.mockResolvedValue({ items: [{ id: 's1' }], total: 1 });
    aprobarAnulacion.mockResolvedValue({});
    rechazarAnulacion.mockResolvedValue({});
    const { result } = renderHook(() => useAnulacionesPendientes(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    await act(() => result.current.aprobar('s1', 'ok'));
    expect(aprobarAnulacion).toHaveBeenCalledWith(SESSION, 's1', 'ok');
    await act(() => result.current.rechazar('s1', 'no'));
    expect(rechazarAnulacion).toHaveBeenCalledWith(SESSION, 's1', 'no');
  });

  it('useAnulacionesPendientes items raw array', async () => {
    listAnulacionesPendientes.mockResolvedValue([{ id: 'x' }]);
    const { result } = renderHook(() => useAnulacionesPendientes(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });

  it('useAnulacionesPendientes error', async () => {
    listAnulacionesPendientes.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAnulacionesPendientes(SESSION));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('useAnulacionesPendientes sin session NO fetch', () => {
    renderHook(() => useAnulacionesPendientes(null));
    expect(listAnulacionesPendientes).not.toHaveBeenCalled();
  });

  it('useBuscarRadicados respeta enabled', async () => {
    buscarRadicados.mockResolvedValueOnce({ items: [], total: 0 });
    renderHook(() => useBuscarRadicados(SESSION, {}, { enabled: false }));
    expect(buscarRadicados).not.toHaveBeenCalled();
  });

  it('useBuscarRadicados enabled true fetch', async () => {
    buscarRadicados.mockResolvedValue({ items: [{ id: 'r1' }], total: 1 });
    const { result } = renderHook(() =>
      useBuscarRadicados(SESSION, { q: 'x' }, { enabled: true }),
    );
    // Forzar refresh manual (cubre la ruta enabled=true).
    await act(() => result.current.refresh());
    expect(result.current.items).toHaveLength(1);
  });

  it('useBuscarRadicados items raw array', async () => {
    buscarRadicados.mockResolvedValue([{ id: 'x' }]);
    const { result } = renderHook(() =>
      useBuscarRadicados(SESSION, { q: 'y' }, { enabled: true }),
    );
    await act(() => result.current.refresh());
    expect(result.current.items).toHaveLength(1);
  });

  it('useBuscarRadicados error', async () => {
    buscarRadicados.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() =>
      useBuscarRadicados(SESSION, { q: 'z' }, { enabled: true }),
    );
    await act(() => result.current.refresh());
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('useReportesVentanilla carga + exportar', async () => {
    getReportesVentanilla.mockResolvedValue({ totales: { radicados: 1 } });
    exportarReporteVentanilla.mockResolvedValue({ export_id: 'e1' });
    const { result } = renderHook(() => useReportesVentanilla(SESSION, {}));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.totales.radicados).toBe(1);
    const r = await act(() => result.current.exportar('pdf'));
    expect(r.export_id).toBe('e1');
  });

  it('useReportesVentanilla error', async () => {
    getReportesVentanilla.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useReportesVentanilla(SESSION, {}));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('useReportesVentanilla sin session NO fetch', () => {
    renderHook(() => useReportesVentanilla(null, {}));
    expect(getReportesVentanilla).not.toHaveBeenCalled();
  });
});
