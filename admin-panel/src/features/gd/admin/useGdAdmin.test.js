import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listUsuariosGd: vi.fn(),
  getUsuarioGd: vi.fn(),
  crearUsuarioGd: vi.fn(),
  actualizarUsuarioGd: vi.fn(),
  asignarRolUsuarioGd: vi.fn(),
  removerRolUsuarioGd: vi.fn(),
  inactivarUsuarioGd: vi.fn(),
  reactivarUsuarioGd: vi.fn(),
  getEstructuraOrganica: vi.fn(),
  crearDependencia: vi.fn(),
  actualizarDependencia: vi.fn(),
  reubicarDependencia: vi.fn(),
  inactivarDependencia: vi.fn(),
  listCatalogos: vi.fn(),
  listItemsCatalogo: vi.fn(),
  crearItemCatalogo: vi.fn(),
  actualizarItemCatalogo: vi.fn(),
  inactivarItemCatalogo: vi.fn(),
  listParametros: vi.fn(),
  actualizarParametro: vi.fn(),
  getCalendarioLaboral: vi.fn(),
  agregarDiaFestivo: vi.fn(),
  quitarDiaFestivo: vi.fn(),
  listPlantillasNotificacion: vi.fn(),
  actualizarPlantillaNotificacion: vi.fn(),
  probarPlantillaNotificacion: vi.fn(),
  getPoliticaRetencionLogs: vi.fn(),
  actualizarPoliticaRetencionLogs: vi.fn(),
  getEstadoBackups: vi.fn(),
  dispararBackupManual: vi.fn(),
  listIntegraciones: vi.fn(),
  actualizarIntegracion: vi.fn(),
  probarIntegracion: vi.fn(),
  getConfigSeguridad: vi.fn(),
  actualizarConfigSeguridad: vi.fn(),
  listSesionesActivas: vi.fn(),
  revocarSesion: vi.fn(),
  getSaludSistema: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useUsuariosGd, useUsuarioGd, useEstructuraOrganica,
  useCatalogosLista, useItemsCatalogo,
  useParametros, useCalendarioLaboral,
  usePlantillasNotificacion, usePoliticaRetencionLogs,
  useEstadoBackups, useIntegraciones,
  useConfigSeguridad, useSesionesActivas, useSaludSistema,
  useCrearUsuarioGd, useActualizarUsuarioGd, useAsignarRolUsuarioGd,
  useRemoverRolUsuarioGd, useInactivarUsuarioGd, useReactivarUsuarioGd,
  useCrearDependencia, useActualizarDependencia, useReubicarDependencia,
  useInactivarDependencia,
  useCrearItemCatalogo, useActualizarItemCatalogo, useInactivarItemCatalogo,
  useActualizarParametro,
  useAgregarDiaFestivo, useQuitarDiaFestivo,
  useActualizarPlantillaNotificacion, useProbarPlantillaNotificacion,
  useActualizarPoliticaRetencionLogs, useDispararBackupManual,
  useActualizarIntegracion, useProbarIntegracion,
  useActualizarConfigSeguridad, useRevocarSesion,
} from './useGdAdmin.js';

const S = { token: 't' };

describe('useUsuariosGd', () => {
  beforeEach(() => vi.clearAllMocks());
  it('items+total', async () => {
    api.listUsuariosGd.mockResolvedValue({ items: [{ id: 'u1' }], total: 1 });
    const { result } = renderHook(() => useUsuariosGd(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array', async () => {
    api.listUsuariosGd.mockResolvedValue([{ id: 'u1' }]);
    const { result } = renderHook(() => useUsuariosGd(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('sin session', () => {
    renderHook(() => useUsuariosGd(null));
    expect(api.listUsuariosGd).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.listUsuariosGd.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useUsuariosGd(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useUsuarioGd', () => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api.getUsuarioGd.mockResolvedValue({ id: 'u1' });
    const { result } = renderHook(() => useUsuarioGd(S, 'u1'));
    await waitFor(() => expect(result.current.data?.id).toBe('u1'));
  });
  it('disabled', () => {
    renderHook(() => useUsuarioGd(S, 'u1', { enabled: false }));
    expect(api.getUsuarioGd).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getUsuarioGd.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useUsuarioGd(S, 'u1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe.each([
  ['useEstructuraOrganica', useEstructuraOrganica, 'getEstructuraOrganica'],
  ['useParametros', useParametros, 'listParametros'],
  ['usePoliticaRetencionLogs', usePoliticaRetencionLogs, 'getPoliticaRetencionLogs'],
  ['useEstadoBackups', useEstadoBackups, 'getEstadoBackups'],
  ['useConfigSeguridad', useConfigSeguridad, 'getConfigSeguridad'],
  ['useSaludSistema', useSaludSistema, 'getSaludSistema'],
])('%s', (_n, hook, apiName) => {
  beforeEach(() => vi.clearAllMocks());
  it('carga', async () => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    await waitFor(() => expect(result.current.data).toBeTruthy());
  });
  it('disabled', () => {
    renderHook(() => hook(S, { enabled: false }));
    expect(api[apiName]).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api[apiName].mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => hook(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useCatalogosLista + useItemsCatalogo + usePlantillasNotif + useIntegraciones + useSesionesActivas', () => {
  beforeEach(() => vi.clearAllMocks());
  it('useCatalogosLista carga items', async () => {
    api.listCatalogos.mockResolvedValue([{ codigo: 'canales' }]);
    const { result } = renderHook(() => useCatalogosLista(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useCatalogosLista error', async () => {
    api.listCatalogos.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCatalogosLista(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useItemsCatalogo disabled', () => {
    renderHook(() => useItemsCatalogo(S, 'canales', { enabled: false }));
    expect(api.listItemsCatalogo).not.toHaveBeenCalled();
  });
  it('useItemsCatalogo carga', async () => {
    api.listItemsCatalogo.mockResolvedValue({ items: [{ id: 'c1' }] });
    const { result } = renderHook(() => useItemsCatalogo(S, 'canales'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useItemsCatalogo array', async () => {
    api.listItemsCatalogo.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useItemsCatalogo(S, 'canales'));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useItemsCatalogo error', async () => {
    api.listItemsCatalogo.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useItemsCatalogo(S, 'canales'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useCalendarioLaboral carga', async () => {
    api.getCalendarioLaboral.mockResolvedValue({ festivos: [] });
    const { result } = renderHook(() => useCalendarioLaboral(S, 2026));
    await waitFor(() => expect(result.current.data).toBeTruthy());
  });
  it('useCalendarioLaboral sin anio no fetch', () => {
    renderHook(() => useCalendarioLaboral(S, null));
    expect(api.getCalendarioLaboral).not.toHaveBeenCalled();
  });
  it('useCalendarioLaboral error', async () => {
    api.getCalendarioLaboral.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCalendarioLaboral(S, 2026));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('usePlantillasNotificacion carga', async () => {
    api.listPlantillasNotificacion.mockResolvedValue([{ codigo: 'pq-asignada' }]);
    const { result } = renderHook(() => usePlantillasNotificacion(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('usePlantillasNotificacion error', async () => {
    api.listPlantillasNotificacion.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePlantillasNotificacion(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useIntegraciones carga', async () => {
    api.listIntegraciones.mockResolvedValue([{ codigo: 'smtp' }]);
    const { result } = renderHook(() => useIntegraciones(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useIntegraciones error', async () => {
    api.listIntegraciones.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useIntegraciones(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('useSesionesActivas carga', async () => {
    api.listSesionesActivas.mockResolvedValue({ items: [{ id: 's1' }], total: 1 });
    const { result } = renderHook(() => useSesionesActivas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useSesionesActivas array', async () => {
    api.listSesionesActivas.mockResolvedValue([{ id: 's1' }]);
    const { result } = renderHook(() => useSesionesActivas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('useSesionesActivas error', async () => {
    api.listSesionesActivas.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useSesionesActivas(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('mutators admin', () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ['crearUsuario', useCrearUsuarioGd, 'crearUsuarioGd'],
    ['actUsuario', useActualizarUsuarioGd, 'actualizarUsuarioGd'],
    ['asignarRol', useAsignarRolUsuarioGd, 'asignarRolUsuarioGd'],
    ['removerRol', useRemoverRolUsuarioGd, 'removerRolUsuarioGd'],
    ['inactivarUsr', useInactivarUsuarioGd, 'inactivarUsuarioGd'],
    ['reactivarUsr', useReactivarUsuarioGd, 'reactivarUsuarioGd'],
    ['crearDep', useCrearDependencia, 'crearDependencia'],
    ['actDep', useActualizarDependencia, 'actualizarDependencia'],
    ['reubicarDep', useReubicarDependencia, 'reubicarDependencia'],
    ['inactivarDep', useInactivarDependencia, 'inactivarDependencia'],
    ['crearItemCat', useCrearItemCatalogo, 'crearItemCatalogo'],
    ['actItemCat', useActualizarItemCatalogo, 'actualizarItemCatalogo'],
    ['inactivarItemCat', useInactivarItemCatalogo, 'inactivarItemCatalogo'],
    ['actParam', useActualizarParametro, 'actualizarParametro'],
    ['agregarFestivo', useAgregarDiaFestivo, 'agregarDiaFestivo'],
    ['quitarFestivo', useQuitarDiaFestivo, 'quitarDiaFestivo'],
    ['actNotif', useActualizarPlantillaNotificacion, 'actualizarPlantillaNotificacion'],
    ['probarNotif', useProbarPlantillaNotificacion, 'probarPlantillaNotificacion'],
    ['actLogs', useActualizarPoliticaRetencionLogs, 'actualizarPoliticaRetencionLogs'],
    ['backupManual', useDispararBackupManual, 'dispararBackupManual'],
    ['actInt', useActualizarIntegracion, 'actualizarIntegracion'],
    ['probarInt', useProbarIntegracion, 'probarIntegracion'],
    ['actSeg', useActualizarConfigSeguridad, 'actualizarConfigSeguridad'],
    ['revocarSes', useRevocarSesion, 'revocarSesion'],
  ])('%s OK', async (_, hook, apiName) => {
    api[apiName].mockResolvedValue({ ok: true });
    const { result } = renderHook(() => hook(S));
    let r;
    await act(async () => { r = await result.current.submit('x'); });
    expect(r).toEqual({ ok: true });
  });
  it('propaga error', async () => {
    api.crearUsuarioGd.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCrearUsuarioGd(S));
    await act(async () => {
      await expect(result.current.submit({})).rejects.toThrow('boom');
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
