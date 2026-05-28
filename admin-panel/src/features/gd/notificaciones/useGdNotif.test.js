import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listNotificacionesInbox: vi.fn(),
  marcarNotifLeida: vi.fn(),
  marcarNotifsTodasLeidas: vi.fn(),
  getPreferenciasNotif: vi.fn(),
  actualizarPreferenciasNotif: vi.fn(),
  listAlertasCriticas: vi.fn(),
  atenderAlertaCritica: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import {
  useNotificacionesInbox, useMarcarNotifLeida, useMarcarTodasLeidas,
  usePreferenciasNotif, useActualizarPreferenciasNotif,
  useAlertasCriticas, useAtenderAlerta,
} from './useGdNotif.js';

const S = { token: 't' };

beforeEach(() => vi.clearAllMocks());

describe('useNotificacionesInbox', () => {
  it('items + no_leidas', async () => {
    api.listNotificacionesInbox.mockResolvedValue({
      items: [{ id: 'n1', leida: false }, { id: 'n2', leida: true }],
      total: 2, no_leidas: 1,
    });
    const { result } = renderHook(() => useNotificacionesInbox(S));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.noLeidas).toBe(1);
  });
  it('calcula noLeidas si no viene', async () => {
    api.listNotificacionesInbox.mockResolvedValue({
      items: [{ id: 'n1', leida: false }, { id: 'n2', leida: false }],
    });
    const { result } = renderHook(() => useNotificacionesInbox(S));
    await waitFor(() => expect(result.current.noLeidas).toBe(2));
  });
  it('array directo', async () => {
    api.listNotificacionesInbox.mockResolvedValue([{ id: 'n1', leida: true }]);
    const { result } = renderHook(() => useNotificacionesInbox(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listNotificacionesInbox.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useNotificacionesInbox(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useNotificacionesInbox(null));
    expect(api.listNotificacionesInbox).not.toHaveBeenCalled();
  });
});

describe('useMarcarNotifLeida', () => {
  it('ok', async () => {
    api.marcarNotifLeida.mockResolvedValue({});
    const { result } = renderHook(() => useMarcarNotifLeida(S));
    await act(async () => { await result.current.submit('n1'); });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.marcarNotifLeida.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useMarcarNotifLeida(S));
    await act(async () => {
      try { await result.current.submit('n1'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useMarcarNotifLeida(null));
    expect(await result.current.submit('n1')).toBeNull();
  });
});

describe('useMarcarTodasLeidas', () => {
  it('ok', async () => {
    api.marcarNotifsTodasLeidas.mockResolvedValue({});
    const { result } = renderHook(() => useMarcarTodasLeidas(S));
    await act(async () => { await result.current.submit(); });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.marcarNotifsTodasLeidas.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useMarcarTodasLeidas(S));
    await act(async () => {
      try { await result.current.submit(); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useMarcarTodasLeidas(null));
    expect(await result.current.submit()).toBeNull();
  });
});

describe('usePreferenciasNotif', () => {
  it('data', async () => {
    api.getPreferenciasNotif.mockResolvedValue({
      canales: { email: true, push: false },
      por_tipo: {},
    });
    const { result } = renderHook(() => usePreferenciasNotif(S));
    await waitFor(() => expect(result.current.data?.canales?.email).toBe(true));
  });
  it('error', async () => {
    api.getPreferenciasNotif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePreferenciasNotif(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => usePreferenciasNotif(null));
    expect(api.getPreferenciasNotif).not.toHaveBeenCalled();
  });
});

describe('useActualizarPreferenciasNotif', () => {
  it('ok', async () => {
    api.actualizarPreferenciasNotif.mockResolvedValue({ aplicado: true });
    const { result } = renderHook(() => useActualizarPreferenciasNotif(S));
    await act(async () => {
      await result.current.submit({ canales: { email: false } });
    });
    expect(result.current.result.aplicado).toBe(true);
  });
  it('error', async () => {
    api.actualizarPreferenciasNotif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useActualizarPreferenciasNotif(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useActualizarPreferenciasNotif(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useAlertasCriticas', () => {
  it('items + totalPendientes', async () => {
    api.listAlertasCriticas.mockResolvedValue({
      items: [{ id: 'a1', categoria: 'vencimiento', severidad: 'alta', atendida_por: null },
              { id: 'a2', categoria: 'sla', severidad: 'media', atendida_por: 'u1' }],
      total_pendientes: 1,
    });
    const { result } = renderHook(() => useAlertasCriticas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.totalPendientes).toBe(1);
  });
  it('calcula totalPendientes si no viene', async () => {
    api.listAlertasCriticas.mockResolvedValue({
      items: [{ id: 'a1', atendida_por: null },
              { id: 'a2', atendida_por: null }],
    });
    const { result } = renderHook(() => useAlertasCriticas(S));
    await waitFor(() => expect(result.current.totalPendientes).toBe(2));
  });
  it('array directo', async () => {
    api.listAlertasCriticas.mockResolvedValue([{ id: 'a1', atendida_por: null }]);
    const { result } = renderHook(() => useAlertasCriticas(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listAlertasCriticas.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAlertasCriticas(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useAlertasCriticas(null));
    expect(api.listAlertasCriticas).not.toHaveBeenCalled();
  });
});

describe('useAtenderAlerta', () => {
  it('ok', async () => {
    api.atenderAlertaCritica.mockResolvedValue({});
    const { result } = renderHook(() => useAtenderAlerta(S));
    await act(async () => { await result.current.submit('a1', 'atendida'); });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.atenderAlertaCritica.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAtenderAlerta(S));
    await act(async () => {
      try { await result.current.submit('a1', 'x'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useAtenderAlerta(null));
    expect(await result.current.submit('a1', 'x')).toBeNull();
  });
});
