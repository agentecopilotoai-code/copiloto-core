import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  listAuditoria: vi.fn(),
}));

import { listAuditoria } from '../services/gdApi.js';
import { useGdAudit } from './useGdAudit.js';

const SESSION = { token: 't', tenant: { id: 'tnt-1' } };

describe('useGdAudit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('llama listAuditoria con los args correctos y guarda items', async () => {
    listAuditoria.mockResolvedValueOnce({
      items: [{ id: 'e1', tipo_evento: 'X' }],
    });
    const { result } = renderHook(() =>
      useGdAudit({
        session: SESSION,
        entidadTipo: 'radicado',
        entidadId: 'r1',
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listAuditoria).toHaveBeenCalledWith(SESSION, {
      entidadTipo: 'radicado',
      entidadId: 'r1',
      limit: 50,
    });
    expect(result.current.events).toHaveLength(1);
  });

  it('no hace fetch si falta entidadId / entidadTipo / session', async () => {
    const { result } = renderHook(() =>
      useGdAudit({ session: SESSION, entidadTipo: null, entidadId: 'r1' }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listAuditoria).not.toHaveBeenCalled();
    expect(result.current.events).toEqual([]);
  });

  it('captura error y lo expone', async () => {
    const err = new Error('boom');
    listAuditoria.mockRejectedValueOnce(err);
    const { result } = renderHook(() =>
      useGdAudit({
        session: SESSION, entidadTipo: 'r', entidadId: 'r1',
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(err);
    expect(result.current.events).toEqual([]);
  });

  it('refresh dispara nuevo fetch', async () => {
    listAuditoria
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [{ id: 'e2', tipo_evento: 'Y' }] });
    const { result } = renderHook(() =>
      useGdAudit({
        session: SESSION, entidadTipo: 'r', entidadId: 'r1',
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.refresh());
    expect(result.current.events).toHaveLength(1);
  });

  it('enabled=false evita fetch', async () => {
    const { result } = renderHook(() =>
      useGdAudit({
        session: SESSION, entidadTipo: 'r', entidadId: 'r1', enabled: false,
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listAuditoria).not.toHaveBeenCalled();
  });

  it('items no-array se normaliza a []', async () => {
    listAuditoria.mockResolvedValueOnce({ items: null });
    const { result } = renderHook(() =>
      useGdAudit({ session: SESSION, entidadTipo: 'r', entidadId: 'r1' }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.events).toEqual([]);
  });
});
