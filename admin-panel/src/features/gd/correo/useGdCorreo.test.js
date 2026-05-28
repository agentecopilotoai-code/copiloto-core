import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listCorreoEntrante: vi.fn(),
  getCorreoEntrante: vi.fn(),
  convertirCorreoARadicado: vi.fn(),
  descartarCorreo: vi.fn(),
  enviarCorreoSaliente: vi.fn(),
  listPlantillasCorreo: vi.fn(),
  listConfigCanalesEmail: vi.fn(),
  actualizarConfigCanalEmail: vi.fn(),
  probarCanalEmail: vi.fn(),
  listReglasAutoClasif: vi.fn(),
  crearReglaAutoClasif: vi.fn(),
  actualizarReglaAutoClasif: vi.fn(),
  eliminarReglaAutoClasif: vi.fn(),
  getSaludCorreo: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useCorreoEntrante, useCorreoEntranteItem,
  useConvertirARadicado, useDescartarCorreo,
  useCorreoComposer, usePlantillasCorreo,
  useConfigCanalesEmail, useActualizarCanalEmail, useProbarCanalEmail,
  useReglasAutoClasif, useCrearReglaAutoClasif,
  useActualizarReglaAutoClasif, useEliminarReglaAutoClasif,
  useSaludCorreo,
} from './useGdCorreo.js';

const S = { token: 't' };

beforeEach(() => vi.clearAllMocks());

describe('useCorreoEntrante', () => {
  it('items + total', async () => {
    api.listCorreoEntrante.mockResolvedValue({
      items: [{ id: 'e1' }, { id: 'e2' }], total: 2,
    });
    const { result } = renderHook(() => useCorreoEntrante(S));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
  });
  it('array directo', async () => {
    api.listCorreoEntrante.mockResolvedValue([{ id: 'e1' }]);
    const { result } = renderHook(() => useCorreoEntrante(S));
    await waitFor(() => expect(result.current.total).toBe(1));
  });
  it('error', async () => {
    api.listCorreoEntrante.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorreoEntrante(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useCorreoEntrante(null));
    expect(api.listCorreoEntrante).not.toHaveBeenCalled();
  });
});

describe('useCorreoEntranteItem', () => {
  it('data', async () => {
    api.getCorreoEntrante.mockResolvedValue({ id: 'e1', asunto: 'A' });
    const { result } = renderHook(() => useCorreoEntranteItem(S, 'e1'));
    await waitFor(() => expect(result.current.data?.asunto).toBe('A'));
  });
  it('enabled=false skip', () => {
    renderHook(() => useCorreoEntranteItem(S, 'e1', { enabled: false }));
    expect(api.getCorreoEntrante).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.getCorreoEntrante.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorreoEntranteItem(S, 'e1'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin id', () => {
    renderHook(() => useCorreoEntranteItem(S, null));
    expect(api.getCorreoEntrante).not.toHaveBeenCalled();
  });
});

describe('useConvertirARadicado', () => {
  it('ok', async () => {
    api.convertirCorreoARadicado.mockResolvedValue({ radicado_id: 'r1', numero: 'R-001' });
    const { result } = renderHook(() => useConvertirARadicado(S));
    await act(async () => { await result.current.submit('e1', { tipo: 'entrada' }); });
    expect(result.current.result.radicado_id).toBe('r1');
  });
  it('error', async () => {
    api.convertirCorreoARadicado.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useConvertirARadicado(S));
    await act(async () => {
      try { await result.current.submit('e1', {}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session/id', async () => {
    const { result } = renderHook(() => useConvertirARadicado(null));
    expect(await result.current.submit('e1', {})).toBeNull();
  });
});

describe('useDescartarCorreo', () => {
  it('ok', async () => {
    api.descartarCorreo.mockResolvedValue({});
    const { result } = renderHook(() => useDescartarCorreo(S));
    await act(async () => { await result.current.submit('e1', 'spam'); });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.descartarCorreo.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useDescartarCorreo(S));
    await act(async () => {
      try { await result.current.submit('e1', 'x'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useDescartarCorreo(null));
    expect(await result.current.submit('e1', 'x')).toBeNull();
  });
});

describe('useCorreoComposer', () => {
  it('ok', async () => {
    api.enviarCorreoSaliente.mockResolvedValue({ id: 's1', message_id: 'm1' });
    const { result } = renderHook(() => useCorreoComposer(S));
    await act(async () => {
      await result.current.submit({ para: ['a@b.com'], asunto: 'x', cuerpo_html: 'h' });
    });
    expect(result.current.result.id).toBe('s1');
  });
  it('error', async () => {
    api.enviarCorreoSaliente.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCorreoComposer(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useCorreoComposer(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('usePlantillasCorreo', () => {
  it('items', async () => {
    api.listPlantillasCorreo.mockResolvedValue({ items: [{ id: 'p1' }] });
    const { result } = renderHook(() => usePlantillasCorreo(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('array directo', async () => {
    api.listPlantillasCorreo.mockResolvedValue([{ id: 'p1' }]);
    const { result } = renderHook(() => usePlantillasCorreo(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listPlantillasCorreo.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => usePlantillasCorreo(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => usePlantillasCorreo(null));
    expect(api.listPlantillasCorreo).not.toHaveBeenCalled();
  });
});

describe('useConfigCanalesEmail', () => {
  it('items', async () => {
    api.listConfigCanalesEmail.mockResolvedValue({
      items: [{ id: 'c1', tipo: 'SMTP' }, { id: 'c2', tipo: 'IMAP' }],
    });
    const { result } = renderHook(() => useConfigCanalesEmail(S));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
  });
  it('array', async () => {
    api.listConfigCanalesEmail.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useConfigCanalesEmail(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listConfigCanalesEmail.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConfigCanalesEmail(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useConfigCanalesEmail(null));
    expect(api.listConfigCanalesEmail).not.toHaveBeenCalled();
  });
});

describe('useActualizarCanalEmail', () => {
  it('ok', async () => {
    api.actualizarConfigCanalEmail.mockResolvedValue({ id: 'c1', host: 'x' });
    const { result } = renderHook(() => useActualizarCanalEmail(S));
    await act(async () => { await result.current.submit('c1', { host: 'x' }); });
    expect(result.current.result.id).toBe('c1');
  });
  it('error', async () => {
    api.actualizarConfigCanalEmail.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useActualizarCanalEmail(S));
    await act(async () => {
      try { await result.current.submit('c1', {}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useActualizarCanalEmail(null));
    expect(await result.current.submit('c1', {})).toBeNull();
  });
});

describe('useProbarCanalEmail', () => {
  it('ok', async () => {
    api.probarCanalEmail.mockResolvedValue({ ok: true, latencia_ms: 80 });
    const { result } = renderHook(() => useProbarCanalEmail(S));
    await act(async () => { await result.current.submit('c1'); });
    expect(result.current.result.ok).toBe(true);
  });
  it('error', async () => {
    api.probarCanalEmail.mockRejectedValue(new Error('timeout'));
    const { result } = renderHook(() => useProbarCanalEmail(S));
    await act(async () => {
      try { await result.current.submit('c1'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useProbarCanalEmail(null));
    expect(await result.current.submit('c1')).toBeNull();
  });
});

describe('useReglasAutoClasif', () => {
  it('items', async () => {
    api.listReglasAutoClasif.mockResolvedValue({
      items: [{ id: 'r1', nombre: 'reg1', activa: true }],
    });
    const { result } = renderHook(() => useReglasAutoClasif(S));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
  });
  it('error', async () => {
    api.listReglasAutoClasif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useReglasAutoClasif(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useReglasAutoClasif(null));
    expect(api.listReglasAutoClasif).not.toHaveBeenCalled();
  });
});

describe('useCrearReglaAutoClasif', () => {
  it('ok', async () => {
    api.crearReglaAutoClasif.mockResolvedValue({ id: 'r1' });
    const { result } = renderHook(() => useCrearReglaAutoClasif(S));
    await act(async () => { await result.current.submit({ nombre: 'r' }); });
    expect(result.current.result.id).toBe('r1');
  });
  it('error', async () => {
    api.crearReglaAutoClasif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useCrearReglaAutoClasif(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useCrearReglaAutoClasif(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useActualizarReglaAutoClasif', () => {
  it('ok', async () => {
    api.actualizarReglaAutoClasif.mockResolvedValue({ id: 'r1', activa: false });
    const { result } = renderHook(() => useActualizarReglaAutoClasif(S));
    await act(async () => {
      await result.current.submit('r1', { activa: false });
    });
    expect(result.current.result.activa).toBe(false);
  });
  it('error', async () => {
    api.actualizarReglaAutoClasif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useActualizarReglaAutoClasif(S));
    await act(async () => {
      try { await result.current.submit('r1', {}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useActualizarReglaAutoClasif(null));
    expect(await result.current.submit('r1', {})).toBeNull();
  });
});

describe('useEliminarReglaAutoClasif', () => {
  it('ok', async () => {
    api.eliminarReglaAutoClasif.mockResolvedValue({});
    const { result } = renderHook(() => useEliminarReglaAutoClasif(S));
    await act(async () => { await result.current.submit('r1'); });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.eliminarReglaAutoClasif.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useEliminarReglaAutoClasif(S));
    await act(async () => {
      try { await result.current.submit('r1'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useEliminarReglaAutoClasif(null));
    expect(await result.current.submit('r1')).toBeNull();
  });
});

describe('useSaludCorreo', () => {
  it('data', async () => {
    api.getSaludCorreo.mockResolvedValue({
      canales: [{ id: 'c1', ok_pct: 0.99, bounces: 1 }],
      totales: { recibidos: 100, enviados: 50, bounces: 1 },
    });
    const { result } = renderHook(() => useSaludCorreo(S));
    await waitFor(() => expect(result.current.data?.canales).toHaveLength(1));
  });
  it('ventana custom', async () => {
    api.getSaludCorreo.mockResolvedValue({});
    renderHook(() => useSaludCorreo(S, '7d'));
    await waitFor(() => expect(api.getSaludCorreo).toHaveBeenCalledWith(S, '7d'));
  });
  it('error', async () => {
    api.getSaludCorreo.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useSaludCorreo(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useSaludCorreo(null));
    expect(api.getSaludCorreo).not.toHaveBeenCalled();
  });
});
