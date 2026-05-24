import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  GdNoProfileError,
  GdHttpError,
  getMyGdProfile,
  getEntidadPublica,
  listAuditoria,
  listRadicados,
  listMyBuzon,
  crearRadicadoEntrada,
  listPQRSD,
  fetchEntidad,
  _internal,
} from './gdApi.js';

const SESSION = { token: 't0k', tenant: { id: 'tnt-1' } };

function mkResponse({ ok = true, status = 200, body = {} } = {}) {
  return {
    ok, status,
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

describe('gdApi', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('authHeaders incluye Bearer + X-Tenant-Id', () => {
    const h = _internal.authHeaders(SESSION);
    expect(h.Authorization).toBe('Bearer t0k');
    expect(h['X-Tenant-Id']).toBe('tnt-1');
    expect(h['Content-Type']).toBe('application/json');
  });

  it('gdPath usa /api/v1 por default', () => {
    expect(_internal.gdPath({}, '/gd/me')).toBe('/api/v1/gd/me');
  });

  it('getMyGdProfile hace GET /gd/me', async () => {
    globalThis.fetch.mockResolvedValueOnce(
      mkResponse({ body: { user_id: 'u1', estado_gd: 'activo' } }),
    );
    const out = await getMyGdProfile(SESSION);
    expect(out.estado_gd).toBe('activo');
    expect(globalThis.fetch).toHaveBeenCalled();
  });

  it('getEntidadPublica hace GET /gd/entidad', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: { nombre_oficial: 'X' } }));
    const out = await getEntidadPublica(SESSION);
    expect(out.nombre_oficial).toBe('X');
  });

  it('listAuditoria pasa params como query string', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: { items: [] } }));
    await listAuditoria(SESSION, {
      entidadTipo: 'radicado', entidadId: 'r1', limit: 25,
    });
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('entidad_tipo=radicado');
    expect(url).toContain('entidad_id=r1');
    expect(url).toContain('limit=25');
  });

  it('listRadicados acepta scope opcional', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listRadicados(SESSION, { scope: 'institucional', q: 'abc' });
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('scope=institucional');
    expect(url).toContain('q=abc');
  });

  it('listMyBuzon llama /gd/me/buzon', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listMyBuzon(SESSION);
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/me/buzon');
  });

  it('crearRadicadoEntrada POST con body', async () => {
    globalThis.fetch.mockResolvedValueOnce(
      mkResponse({ status: 201, body: { id: 'r1' } }),
    );
    const out = await crearRadicadoEntrada(SESSION, { asunto: 'X' });
    expect(out.id).toBe('r1');
    expect(globalThis.fetch.mock.calls[0][1].method).toBe('POST');
  });

  it('listPQRSD construye query', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listPQRSD(SESSION, { estado: 'asignada' });
    expect(globalThis.fetch.mock.calls[0][0]).toContain('estado=asignada');
  });

  it('fetchEntidad GET genérico', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkResponse({ body: { x: 1 } }));
    const out = await fetchEntidad(SESSION, '/gd/algo/x');
    expect(out).toEqual({ x: 1 });
  });

  it('403 con code=gd_profile_missing_or_inactive lanza GdNoProfileError', async () => {
    globalThis.fetch.mockResolvedValueOnce(
      mkResponse({
        ok: false, status: 403,
        body: { detail: { code: 'gd_profile_missing_or_inactive' } },
      }),
    );
    await expect(getMyGdProfile(SESSION)).rejects.toBeInstanceOf(GdNoProfileError);
  });

  it('otros HTTP errores lanzan GdHttpError con status', async () => {
    globalThis.fetch.mockResolvedValueOnce(
      mkResponse({ ok: false, status: 500, body: { detail: 'boom' } }),
    );
    await expect(getMyGdProfile(SESSION)).rejects.toMatchObject({
      status: 500,
      name: 'GdHttpError',
    });
  });

  it('body vacío (text="") es null', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true, status: 204, text: () => Promise.resolve(''),
    });
    const out = await getMyGdProfile(SESSION);
    expect(out).toBeNull();
  });

  it('body NO json no rompe (devuelve null)', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true, status: 200, text: () => Promise.resolve('plain text'),
    });
    const out = await getMyGdProfile(SESSION);
    expect(out).toBeNull();
  });
});

describe('gdApi — endpoints ventanilla (UI-2)', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mkOk(body) {
    return {
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify(body)),
    };
  }

  it('crearRadicadoEntrada POST /gd/ventanilla/radicados/entrada', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ id: 'r1' }));
    const mod = await import('./gdApi.js');
    const out = await mod.crearRadicadoEntrada({}, { asunto: 'X' });
    expect(out.id).toBe('r1');
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/ventanilla/radicados/entrada');
    expect(globalThis.fetch.mock.calls[0][1].method).toBe('POST');
  });

  it('crearRadicadoSalida POST', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ id: 's1' }));
    const mod = await import('./gdApi.js');
    await mod.crearRadicadoSalida({}, { asunto: 'Y' });
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/ventanilla/radicados/salida');
  });

  it('clasificarRadicado POST', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ ok: true }));
    const mod = await import('./gdApi.js');
    await mod.clasificarRadicado({}, 'r1', { tipo_clasificacion: 'pqrsd' });
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/ventanilla/radicados/r1/clasificar');
  });

  it('listColaPendientesClasificacion con filtros', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ items: [] }));
    const mod = await import('./gdApi.js');
    await mod.listColaPendientesClasificacion({}, { canal_id: 'web', limit: 25 });
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('/gd/ventanilla/cola/pendientes-clasificacion');
    expect(url).toContain('canal_id=web');
    expect(url).toContain('limit=25');
  });

  it('verificarConstanciaPublica (sin session)', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ numero_radicado: '2026-E-1' }));
    const mod = await import('./gdApi.js');
    const r = await mod.verificarConstanciaPublica('AB12');
    expect(r.numero_radicado).toBe('2026-E-1');
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/ventanilla/constancias/AB12');
  });

  it('verificarConstanciaPublica error', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: false, status: 404,
      text: () => Promise.resolve('{"detail":"no existe"}'),
    });
    const mod = await import('./gdApi.js');
    await expect(mod.verificarConstanciaPublica('NOPE')).rejects.toMatchObject({
      status: 404, name: 'GdHttpError',
    });
  });

  it('listCanales GET', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk([{ id: 'c1' }]));
    const mod = await import('./gdApi.js');
    await mod.listCanales({});
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/catalogos/canales');
  });

  it('buscarTerceros con q', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk([]));
    const mod = await import('./gdApi.js');
    await mod.buscarTerceros({}, 'Juan', { limit: 5 });
    expect(globalThis.fetch.mock.calls[0][0]).toMatch(/q=Juan.*limit=5|limit=5.*q=Juan/);
  });

  it('crearTercero POST con body', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ id: 't1' }));
    const mod = await import('./gdApi.js');
    await mod.crearTercero({}, { nombre_completo: 'X' });
    expect(globalThis.fetch.mock.calls[0][1].method).toBe('POST');
  });

  it('listDependencias GET', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk([]));
    const mod = await import('./gdApi.js');
    await mod.listDependencias({});
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/estructura/dependencias');
  });

  it('sugerenciaIaExtraer POST', async () => {
    globalThis.fetch.mockResolvedValueOnce(mkOk({ resumen: 'R' }));
    const mod = await import('./gdApi.js');
    const r = await mod.sugerenciaIaExtraer({}, { asunto: 'X' });
    expect(r.resumen).toBe('R');
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/gd/ia/extraer');
  });
});
