import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  sugerirClasificacionIa: vi.fn(),
  aplicarSugerenciaClasificacion: vi.fn(),
  resumirDocumentoIa: vi.fn(),
  buscarSemanticoIa: vi.fn(),
  registrarFeedbackBusquedaIa: vi.fn(),
  preguntarAsistenteIa: vi.fn(),
  listConversacionesIa: vi.fn(),
  getConversacionIa: vi.fn(),
  detectarPiiIa: vi.fn(),
  reportarFalsoPositivoPii: vi.fn(),
  getUsoIa: vi.fn(),
  getLimitesIa: vi.fn(),
  actualizarLimitesIa: vi.fn(),
  getConfigModelosIa: vi.fn(),
  actualizarConfigModelosIa: vi.fn(),
}));

import * as api from '../services/gdApi.js';
import {
  useSugerenciaClasificacion, useAplicarSugerencia,
  useResumenDoc,
  useBusquedaSemantica, useFeedbackBusqueda,
  useAsistente, useConversacionesIa,
  useDeteccionPII, useFalsoPositivoPii,
  useUsoIa, useLimitesIa, useActualizarLimitesIa,
  useConfigModelosIa, useActualizarConfigModelosIa,
} from './useGdIa.js';

const S = { token: 't' };

beforeEach(() => vi.clearAllMocks());

describe('useSugerenciaClasificacion', () => {
  it('submit éxito', async () => {
    api.sugerirClasificacionIa.mockResolvedValue({ trd_sugerida: { serie: '100' }, confianza: 0.92 });
    const { result } = renderHook(() => useSugerenciaClasificacion(S));
    await act(async () => { await result.current.submit({ contenido: 'x' }); });
    expect(result.current.data.confianza).toBe(0.92);
    expect(result.current.error).toBeNull();
  });
  it('submit error', async () => {
    api.sugerirClasificacionIa.mockRejectedValue(new Error('ia_down'));
    const { result } = renderHook(() => useSugerenciaClasificacion(S));
    await act(async () => {
      try { await result.current.submit({ contenido: 'x' }); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session no llama', async () => {
    const { result } = renderHook(() => useSugerenciaClasificacion(null));
    const r = await result.current.submit({ contenido: 'x' });
    expect(r).toBeNull();
    expect(api.sugerirClasificacionIa).not.toHaveBeenCalled();
  });
});

describe('useAplicarSugerencia', () => {
  it('aplica decisión', async () => {
    api.aplicarSugerenciaClasificacion.mockResolvedValue({ aplicado: true, audit_id: 'a1' });
    const { result } = renderHook(() => useAplicarSugerencia(S));
    await act(async () => {
      await result.current.submit({ entidad: 'documento', entidad_id: 'd1', decision: 'aceptar' });
    });
    expect(result.current.result.aplicado).toBe(true);
  });
  it('error', async () => {
    api.aplicarSugerenciaClasificacion.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAplicarSugerencia(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useAplicarSugerencia(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useResumenDoc', () => {
  it('resumen ok', async () => {
    api.resumirDocumentoIa.mockResolvedValue({ resumen: 'X', tokens: 100 });
    const { result } = renderHook(() => useResumenDoc(S));
    await act(async () => { await result.current.submit({ entidad: 'documento', entidad_id: 'd1' }); });
    expect(result.current.data.resumen).toBe('X');
  });
  it('error', async () => {
    api.resumirDocumentoIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useResumenDoc(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useResumenDoc(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useBusquedaSemantica', () => {
  it('items + modelo', async () => {
    api.buscarSemanticoIa.mockResolvedValue({
      resultados: [{ documento_id: 'd1', score: 0.9 }],
      modelo_embeddings: 'text-3', tokens: 50,
    });
    const { result } = renderHook(() => useBusquedaSemantica(S));
    await act(async () => { await result.current.submit({ query: 'políticas' }); });
    expect(result.current.resultados).toHaveLength(1);
    expect(result.current.modelo).toBe('text-3');
    expect(result.current.lastQuery).toBe('políticas');
  });
  it('payload sin resultados → []', async () => {
    api.buscarSemanticoIa.mockResolvedValue({});
    const { result } = renderHook(() => useBusquedaSemantica(S));
    await act(async () => { await result.current.submit({ query: 'x' }); });
    expect(result.current.resultados).toEqual([]);
  });
  it('error', async () => {
    api.buscarSemanticoIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useBusquedaSemantica(S));
    await act(async () => {
      try { await result.current.submit({ query: 'x' }); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useBusquedaSemantica(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useFeedbackBusqueda', () => {
  it('envia ok', async () => {
    api.registrarFeedbackBusquedaIa.mockResolvedValue({});
    const { result } = renderHook(() => useFeedbackBusqueda(S));
    await act(async () => {
      await result.current.submit({ query: 'x', documento_id: 'd1', util: true });
    });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.registrarFeedbackBusquedaIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useFeedbackBusqueda(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useFeedbackBusqueda(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useAsistente', () => {
  it('envia mensaje y acumula citas', async () => {
    api.preguntarAsistenteIa.mockResolvedValue({
      conversacion_id: 'c1', respuesta: 'Sí, según el doc X.',
      citas: [{ documento_id: 'd1', fragmento: '...' }],
    });
    const { result } = renderHook(() => useAsistente(S));
    await act(async () => { await result.current.enviar('¿estado del proceso?'); });
    expect(result.current.conversacionId).toBe('c1');
    expect(result.current.mensajes).toHaveLength(2);
    expect(result.current.citasUltima).toHaveLength(1);
  });
  it('reset limpia', async () => {
    api.preguntarAsistenteIa.mockResolvedValue({ conversacion_id: 'c1', respuesta: 'ok', citas: [] });
    const { result } = renderHook(() => useAsistente(S));
    await act(async () => { await result.current.enviar('hi'); });
    act(() => { result.current.reset(); });
    expect(result.current.mensajes).toEqual([]);
    expect(result.current.conversacionId).toBeNull();
  });
  it('mensaje vacío no llama', async () => {
    const { result } = renderHook(() => useAsistente(S));
    const r = await result.current.enviar('');
    expect(r).toBeNull();
    expect(api.preguntarAsistenteIa).not.toHaveBeenCalled();
  });
  it('error', async () => {
    api.preguntarAsistenteIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAsistente(S));
    await act(async () => {
      try { await result.current.enviar('x'); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('carga histórico cuando trae conversacionId', async () => {
    api.getConversacionIa.mockResolvedValue({
      id: 'c9', titulo: 'previa',
      mensajes: [{ rol: 'user', contenido: 'hola' }],
    });
    const { result } = renderHook(() => useAsistente(S, 'c9'));
    await waitFor(() => expect(result.current.mensajes).toHaveLength(1));
  });
  it('error al cargar histórico', async () => {
    api.getConversacionIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useAsistente(S, 'c9'));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
});

describe('useConversacionesIa', () => {
  it('items+total', async () => {
    api.listConversacionesIa.mockResolvedValue({
      items: [{ id: 'c1' }, { id: 'c2' }], total: 2,
    });
    const { result } = renderHook(() => useConversacionesIa(S));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
  });
  it('array directo', async () => {
    api.listConversacionesIa.mockResolvedValue([{ id: 'c1' }]);
    const { result } = renderHook(() => useConversacionesIa(S));
    await waitFor(() => expect(result.current.total).toBe(1));
  });
  it('error', async () => {
    api.listConversacionesIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConversacionesIa(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useConversacionesIa(null));
    expect(api.listConversacionesIa).not.toHaveBeenCalled();
  });
});

describe('useDeteccionPII', () => {
  it('detecta hallazgos', async () => {
    api.detectarPiiIa.mockResolvedValue({
      detectado: true,
      hallazgos: [{ tipo: 'cedula', severidad: 'alta', categoria_ley1581: 'datos_sensibles' }],
    });
    const { result } = renderHook(() => useDeteccionPII(S));
    await act(async () => { await result.current.submit({ contenido: 'CC 123' }); });
    expect(result.current.data.detectado).toBe(true);
  });
  it('error', async () => {
    api.detectarPiiIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useDeteccionPII(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useDeteccionPII(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useFalsoPositivoPii', () => {
  it('ok', async () => {
    api.reportarFalsoPositivoPii.mockResolvedValue({});
    const { result } = renderHook(() => useFalsoPositivoPii(S));
    await act(async () => {
      await result.current.submit({ hallazgo_id: 'h1', motivo: 'no es' });
    });
    expect(result.current.enviado).toBe(true);
  });
  it('error', async () => {
    api.reportarFalsoPositivoPii.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useFalsoPositivoPii(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useFalsoPositivoPii(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useUsoIa', () => {
  it('data ok', async () => {
    api.getUsoIa.mockResolvedValue({
      total_tokens: 1000, total_coste_usd: 1.23,
      por_modelo: [], por_usuario: [], por_funcionalidad: [],
    });
    const { result } = renderHook(() => useUsoIa(S, { from: '2026-01-01' }));
    await waitFor(() => expect(result.current.data?.total_tokens).toBe(1000));
  });
  it('error', async () => {
    api.getUsoIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useUsoIa(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useUsoIa(null));
    expect(api.getUsoIa).not.toHaveBeenCalled();
  });
});

describe('useLimitesIa', () => {
  it('data ok', async () => {
    api.getLimitesIa.mockResolvedValue({ limite_diario_usd: 5, consumido_dia: 1.2 });
    const { result } = renderHook(() => useLimitesIa(S));
    await waitFor(() => expect(result.current.data?.limite_diario_usd).toBe(5));
  });
  it('error', async () => {
    api.getLimitesIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useLimitesIa(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useLimitesIa(null));
    expect(api.getLimitesIa).not.toHaveBeenCalled();
  });
});

describe('useActualizarLimitesIa', () => {
  it('ok', async () => {
    api.actualizarLimitesIa.mockResolvedValue({ aplicado: true });
    const { result } = renderHook(() => useActualizarLimitesIa(S));
    await act(async () => {
      await result.current.submit({ usuario_id: 'u1', limite_diario_usd: 10, motivo: 'm' });
    });
    expect(result.current.result.aplicado).toBe(true);
  });
  it('error', async () => {
    api.actualizarLimitesIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useActualizarLimitesIa(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useActualizarLimitesIa(null));
    expect(await result.current.submit({})).toBeNull();
  });
});

describe('useConfigModelosIa', () => {
  it('data ok', async () => {
    api.getConfigModelosIa.mockResolvedValue({
      modelos: [{ codigo: 'gpt-4', activo: true }],
      defaults: { sugerencia: 'gpt-4' },
    });
    const { result } = renderHook(() => useConfigModelosIa(S));
    await waitFor(() => expect(result.current.data?.modelos).toHaveLength(1));
  });
  it('error', async () => {
    api.getConfigModelosIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useConfigModelosIa(S));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
  });
  it('sin session', () => {
    renderHook(() => useConfigModelosIa(null));
    expect(api.getConfigModelosIa).not.toHaveBeenCalled();
  });
});

describe('useActualizarConfigModelosIa', () => {
  it('ok', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const { result } = renderHook(() => useActualizarConfigModelosIa(S));
    await act(async () => {
      await result.current.submit({ codigo: 'gpt-4', temperatura: 0.2 });
    });
    expect(result.current.result.aplicado).toBe(true);
  });
  it('error', async () => {
    api.actualizarConfigModelosIa.mockRejectedValue(new Error('e'));
    const { result } = renderHook(() => useActualizarConfigModelosIa(S));
    await act(async () => {
      try { await result.current.submit({}); } catch (_) {}
    });
    expect(result.current.error).toBeInstanceOf(Error);
  });
  it('sin session', async () => {
    const { result } = renderHook(() => useActualizarConfigModelosIa(null));
    expect(await result.current.submit({})).toBeNull();
  });
});
