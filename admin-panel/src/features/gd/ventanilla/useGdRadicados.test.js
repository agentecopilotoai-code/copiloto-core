import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  crearRadicadoEntrada: vi.fn(),
  crearRadicadoSalida: vi.fn(),
  clasificarRadicado: vi.fn(),
  listColaPendientesClasificacion: vi.fn(),
}));

import {
  crearRadicadoEntrada,
  crearRadicadoSalida,
  clasificarRadicado,
  listColaPendientesClasificacion,
} from '../services/gdApi.js';

import {
  useCrearRadicadoEntrada,
  useCrearRadicadoSalida,
  useColaPendientesClasificacion,
  useClasificarRadicado,
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
