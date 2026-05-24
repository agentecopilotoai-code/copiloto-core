import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listPlantillas: vi.fn(),
  getPlantilla: vi.fn(),
  crearPlantilla: vi.fn(),
  actualizarPlantilla: vi.fn(),
  nuevaVersionPlantilla: vi.fn(),
  inactivarPlantilla: vi.fn(),
  generarDocumentoDePlantilla: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  usePlantillasList, usePlantilla,
  useCrearPlantilla, useActualizarPlantilla,
  useNuevaVersionPlantilla, useInactivarPlantilla,
  useGenerarDocumentoDePlantilla,
} from './useGdPlantillas.js';

const S = { token: 't' };

describe('usePlantillasList', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items + total', async () => {
    api.listPlantillas.mockResolvedValue({ items: [{ id: 'p1' }], total: 1 });
    const { result } = renderHook(() => usePlantillasList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array directo', async () => {
    api.listPlantillas.mockResolvedValue([{ id: 'p1' }]);
    const { result } = renderHook(() => usePlantillasList(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listPlantillas.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePlantillasList(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session no fetch', () => {
    renderHook(() => usePlantillasList(null));
    expect(api.listPlantillas).not.toHaveBeenCalled();
  });
});

describe('usePlantilla', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api.getPlantilla.mockResolvedValue({ id: 'p1', nombre: 'X' });
    const { result } = renderHook(() => usePlantilla(S, 'p1'));
    await waitFor(() => expect(result.current.data?.nombre).toBe('X'));
  });
  it('disabled no fetch', () => {
    renderHook(() => usePlantilla(S, 'p1', { enabled: false }));
    expect(api.getPlantilla).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getPlantilla.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePlantilla(S, 'p1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators plantillas', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['crear', useCrearPlantilla, 'crearPlantilla'],
    ['actualizar', useActualizarPlantilla, 'actualizarPlantilla'],
    ['nuevaVersion', useNuevaVersionPlantilla, 'nuevaVersionPlantilla'],
    ['inactivar', useInactivarPlantilla, 'inactivarPlantilla'],
    ['generar', useGenerarDocumentoDePlantilla, 'generarDocumentoDePlantilla'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ id: 'r' });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ id: 'r' });
  });
  it('propaga error', async () => {
    api.crearPlantilla.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCrearPlantilla(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
