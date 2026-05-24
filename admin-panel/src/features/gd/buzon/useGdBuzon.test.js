import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  getMiBuzon: vi.fn(),
  getBuzonDependencia: vi.fn(),
  getCargaEquipo: vi.fn(),
  getTarea: vi.fn(),
  ejecutarAccionTarea: vi.fn(),
  listUsuariosDependencia: vi.fn(),
  getTareasPendientesUsuario: vi.fn(),
  reasignarTareasLote: vi.fn(),
}));

import {
  getMiBuzon, getBuzonDependencia, getCargaEquipo,
  getTarea, ejecutarAccionTarea, listUsuariosDependencia,
  getTareasPendientesUsuario, reasignarTareasLote,
} from '../services/gdApi.js';

import {
  CARPETAS,
  useMiBuzon,
  useBuzonDependencia,
  useCargaEquipo,
  useTarea,
  useAccionTarea,
  useUsuariosDependencia,
  useTareasPendientesUsuario,
  useReasignarTareasLote,
} from './useGdBuzon.js';

const S = { token: 't' };

describe('CARPETAS', () => {
  it('expone 10 carpetas con id + label + icon', () => {
    expect(CARPETAS).toHaveLength(10);
    expect(CARPETAS.every((c) => c.id && c.label && c.icon)).toBe(true);
  });
});

describe('useMiBuzon', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga items + contadores', async () => {
    getMiBuzon.mockResolvedValue({ items: [{ id: 'i1' }], contadores: { pqrsd: 3 }, total: 1 });
    const { result } = renderHook(() => useMiBuzon(S, { carpeta: 'pqrsd' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.contadores.pqrsd).toBe(3);
  });
  it('error', async () => {
    getMiBuzon.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useMiBuzon(S));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('items raw array', async () => {
    getMiBuzon.mockResolvedValue([{ id: 'x' }]);
    const { result } = renderHook(() => useMiBuzon(S));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });
  it('sin session NO fetch', () => {
    renderHook(() => useMiBuzon(null));
    expect(getMiBuzon).not.toHaveBeenCalled();
  });
});

describe('useBuzonDependencia', () => {
  beforeEach(() => vi.clearAllMocks());
  it('llama getBuzonDependencia con scope', async () => {
    getBuzonDependencia.mockResolvedValue({ items: [], contadores: {}, total: 0 });
    renderHook(() => useBuzonDependencia(S, { carpeta: 'tareas' }));
    await waitFor(() => expect(getBuzonDependencia).toHaveBeenCalled());
  });
});

describe('useCargaEquipo', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga data', async () => {
    getCargaEquipo.mockResolvedValue({ usuarios: [{ user_id: 'u1', nombre: 'X', tareas_abiertas: 5 }] });
    const { result } = renderHook(() => useCargaEquipo(S));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.usuarios).toHaveLength(1);
  });
  it('error', async () => {
    getCargaEquipo.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCargaEquipo(S));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session NO fetch', () => {
    renderHook(() => useCargaEquipo(null));
    expect(getCargaEquipo).not.toHaveBeenCalled();
  });
});

describe('useTarea', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga tarea por id', async () => {
    getTarea.mockResolvedValue({ id: 't1', titulo: 'X', estado: 'asignada' });
    const { result } = renderHook(() => useTarea(S, 't1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data.id).toBe('t1');
  });
  it('disabled NO fetch', () => {
    renderHook(() => useTarea(S, 't1', { enabled: false }));
    expect(getTarea).not.toHaveBeenCalled();
  });
  it('error', async () => {
    getTarea.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTarea(S, 't1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useAccionTarea', () => {
  beforeEach(() => vi.clearAllMocks());
  it('submit OK', async () => {
    ejecutarAccionTarea.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useAccionTarea(S));
    await act(async () => {
      await result.current.submit('t1', 'iniciar', {});
    });
    expect(ejecutarAccionTarea).toHaveBeenCalledWith(S, 't1', 'iniciar', {});
  });
  it('error', async () => {
    ejecutarAccionTarea.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAccionTarea(S));
    await act(async () => {
      await expect(result.current.submit('t1', 'finalizar')).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useUsuariosDependencia', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga + raw array', async () => {
    listUsuariosDependencia.mockResolvedValue([{ id: 'u1', nombre: 'X' }]);
    const { result } = renderHook(() => useUsuariosDependencia(S, 'd1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });
  it('items: { items: [...] }', async () => {
    listUsuariosDependencia.mockResolvedValue({ items: [{ id: 'u1' }] });
    const { result } = renderHook(() => useUsuariosDependencia(S, 'd1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });
  it('sin dependenciaId NO fetch', () => {
    renderHook(() => useUsuariosDependencia(S, null));
    expect(listUsuariosDependencia).not.toHaveBeenCalled();
  });
  it('error', async () => {
    listUsuariosDependencia.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useUsuariosDependencia(S, 'd1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useTareasPendientesUsuario', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: [{ id: 't1' }] });
    const { result } = renderHook(() => useTareasPendientesUsuario(S, 'u1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
  });
  it('sin userId NO fetch', () => {
    renderHook(() => useTareasPendientesUsuario(S, null));
    expect(getTareasPendientesUsuario).not.toHaveBeenCalled();
  });
  it('error', async () => {
    getTareasPendientesUsuario.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useTareasPendientesUsuario(S, 'u1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe('useReasignarTareasLote', () => {
  beforeEach(() => vi.clearAllMocks());
  it('submit OK guarda result', async () => {
    reasignarTareasLote.mockResolvedValue({ reasignadas: 3 });
    const { result } = renderHook(() => useReasignarTareasLote(S));
    await act(async () => {
      const r = await result.current.submit('u1', { tareas: [] });
      expect(r.reasignadas).toBe(3);
    });
    expect(result.current.result.reasignadas).toBe(3);
  });
  it('error', async () => {
    reasignarTareasLote.mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() => useReasignarTareasLote(S));
    await act(async () => {
      await expect(result.current.submit('u1', {})).rejects.toBeTruthy();
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
