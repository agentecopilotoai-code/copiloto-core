import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listCorreosImportados: vi.fn(),
  getCorreoImportado: vi.fn(),
  convertirCorreoARadicado: vi.fn(),
  descartarCorreo: vi.fn(),
  listMisNotificaciones: vi.fn(),
  marcarNotificacionLeida: vi.fn(),
  marcarTodasNotificacionesLeidas: vi.fn(),
  getPreferenciasNotificaciones: vi.fn(),
  actualizarPreferenciasNotificaciones: vi.fn(),
  listAlertas: vi.fn(),
  atenderAlerta: vi.fn(),
  listReglasAlerta: vi.fn(),
  crearReglaAlerta: vi.fn(),
  actualizarReglaAlerta: vi.fn(),
  inactivarReglaAlerta: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useCorreosImportados, useCorreoImportado,
  useConvertirCorreoARadicado, useDescartarCorreo,
  useMisNotificaciones, useMarcarNotificacionLeida,
  useMarcarTodasLeidas,
  usePreferenciasNotificaciones, useActualizarPreferenciasNotificaciones,
  useAlertas, useAtenderAlerta,
  useReglasAlerta, useCrearReglaAlerta,
  useActualizarReglaAlerta, useInactivarReglaAlerta,
} from './useGdComunicaciones.js';

const S = { token: 't' };

describe('readers correo', () => {
  beforeEach(() => vi.clearAllMocks());
  it('useCorreosImportados items+total', async () => {
    api.listCorreosImportados.mockResolvedValue({ items: [{ id: 'c1' }], total: 1 });
    const { result } = renderHook(() => useCorreosImportados(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useCorreosImportados array', async () => {
    api.listCorreosImportados.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useCorreosImportados(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useCorreosImportados error', async () => {
    api.listCorreosImportados.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorreosImportados(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useCorreosImportados sin session', () => {
    renderHook(() => useCorreosImportados(null));
    expect(api.listCorreosImportados).not.toHaveBeenCalled();
  });
  it('useCorreoImportado carga', async () => {
    api.getCorreoImportado.mockResolvedValue({ id: 'c1' });
    const { result } = renderHook(() => useCorreoImportado(S, 'c1'));
    await waitFor(() => expect(result.current.data?.id).toBe('c1'));
  });
  it('useCorreoImportado disabled', () => {
    renderHook(() => useCorreoImportado(S, 'c1', { enabled: false }));
    expect(api.getCorreoImportado).not.toHaveBeenCalled();
  });
  it('useCorreoImportado error', async () => {
    api.getCorreoImportado.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorreoImportado(S, 'c1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('notificaciones + preferencias + alertas + reglas', () => {
  beforeEach(() => vi.clearAllMocks());
  it('useMisNotificaciones items+total', async () => {
    api.listMisNotificaciones.mockResolvedValue({
      items: [{ id: 'n1', leida: false }], total: 1, no_leidas: 1,
    });
    const { result } = renderHook(() => useMisNotificaciones(S));
    await waitFor(() => expect(result.current.no_leidas).toBe(1));
  });
  it('useMisNotificaciones array calcula no_leidas', async () => {
    api.listMisNotificaciones.mockResolvedValue([
      { id: 'n1', leida: false }, { id: 'n2', leida: true },
    ]);
    const { result } = renderHook(() => useMisNotificaciones(S));
    await waitFor(() => expect(result.current.no_leidas).toBe(1));
  });
  it('useMisNotificaciones error', async () => {
    api.listMisNotificaciones.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useMisNotificaciones(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('usePreferenciasNotificaciones carga', async () => {
    api.getPreferenciasNotificaciones.mockResolvedValue({ preferencias: {} });
    const { result } = renderHook(() => usePreferenciasNotificaciones(S));
    await waitFor(() => expect(result.current.data).toBeTruthy());
  });
  it('usePreferenciasNotificaciones error', async () => {
    api.getPreferenciasNotificaciones.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePreferenciasNotificaciones(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useAlertas items+total', async () => {
    api.listAlertas.mockResolvedValue({ items: [{ id: 'a1' }], total: 1 });
    const { result } = renderHook(() => useAlertas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useAlertas array', async () => {
    api.listAlertas.mockResolvedValue([{ id: 'a1' }]);
    const { result } = renderHook(() => useAlertas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useAlertas error', async () => {
    api.listAlertas.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAlertas(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useAlertas sin session', () => {
    renderHook(() => useAlertas(null));
    expect(api.listAlertas).not.toHaveBeenCalled();
  });
  it('useReglasAlerta carga', async () => {
    api.listReglasAlerta.mockResolvedValue([{ id: 'r1' }]);
    const { result } = renderHook(() => useReglasAlerta(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useReglasAlerta error', async () => {
    api.listReglasAlerta.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useReglasAlerta(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators comunicaciones', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['convertir', useConvertirCorreoARadicado, 'convertirCorreoARadicado'],
    ['descartar', useDescartarCorreo, 'descartarCorreo'],
    ['marcar', useMarcarNotificacionLeida, 'marcarNotificacionLeida'],
    ['marcarTodas', useMarcarTodasLeidas, 'marcarTodasNotificacionesLeidas'],
    ['actPrefs', useActualizarPreferenciasNotificaciones, 'actualizarPreferenciasNotificaciones'],
    ['atenderA', useAtenderAlerta, 'atenderAlerta'],
    ['crearR', useCrearReglaAlerta, 'crearReglaAlerta'],
    ['actR', useActualizarReglaAlerta, 'actualizarReglaAlerta'],
    ['inactR', useInactivarReglaAlerta, 'inactivarReglaAlerta'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ ok: true });
  });
  it('propaga error', async () => {
    api.convertirCorreoARadicado.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useConvertirCorreoARadicado(S));
    await act(async () => {
      await expect(result.current.submit('c1', {})).rejects.toThrow('boom');
    });
  });
});
