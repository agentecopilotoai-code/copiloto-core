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
    global.fetch = vi.fn();
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
    global.fetch.mockResolvedValueOnce(
      mkResponse({ body: { user_id: 'u1', estado_gd: 'activo' } }),
    );
    const out = await getMyGdProfile(SESSION);
    expect(out.estado_gd).toBe('activo');
    expect(global.fetch).toHaveBeenCalled();
  });

  it('getEntidadPublica hace GET /gd/entidad', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: { nombre_oficial: 'X' } }));
    const out = await getEntidadPublica(SESSION);
    expect(out.nombre_oficial).toBe('X');
  });

  it('listAuditoria pasa params como query string', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: { items: [] } }));
    await listAuditoria(SESSION, {
      entidadTipo: 'radicado', entidadId: 'r1', limit: 25,
    });
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('entidad_tipo=radicado');
    expect(url).toContain('entidad_id=r1');
    expect(url).toContain('limit=25');
  });

  it('listRadicados acepta scope opcional', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listRadicados(SESSION, { scope: 'institucional', q: 'abc' });
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('scope=institucional');
    expect(url).toContain('q=abc');
  });

  it('listMyBuzon llama /gd/me/buzon', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listMyBuzon(SESSION);
    expect(global.fetch.mock.calls[0][0]).toContain('/gd/me/buzon');
  });

  it('crearRadicadoEntrada POST con body', async () => {
    global.fetch.mockResolvedValueOnce(
      mkResponse({ status: 201, body: { id: 'r1' } }),
    );
    const out = await crearRadicadoEntrada(SESSION, { asunto: 'X' });
    expect(out.id).toBe('r1');
    expect(global.fetch.mock.calls[0][1].method).toBe('POST');
  });

  it('listPQRSD construye query', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: [] }));
    await listPQRSD(SESSION, { estado: 'asignada' });
    expect(global.fetch.mock.calls[0][0]).toContain('estado=asignada');
  });

  it('fetchEntidad GET genérico', async () => {
    global.fetch.mockResolvedValueOnce(mkResponse({ body: { x: 1 } }));
    const out = await fetchEntidad(SESSION, '/gd/algo/x');
    expect(out).toEqual({ x: 1 });
  });

  it('403 con code=gd_profile_missing_or_inactive lanza GdNoProfileError', async () => {
    global.fetch.mockResolvedValueOnce(
      mkResponse({
        ok: false, status: 403,
        body: { detail: { code: 'gd_profile_missing_or_inactive' } },
      }),
    );
    await expect(getMyGdProfile(SESSION)).rejects.toBeInstanceOf(GdNoProfileError);
  });

  it('otros HTTP errores lanzan GdHttpError con status', async () => {
    global.fetch.mockResolvedValueOnce(
      mkResponse({ ok: false, status: 500, body: { detail: 'boom' } }),
    );
    await expect(getMyGdProfile(SESSION)).rejects.toMatchObject({
      status: 500,
      name: 'GdHttpError',
    });
  });

  it('body vacío (text="") es null', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true, status: 204, text: () => Promise.resolve(''),
    });
    const out = await getMyGdProfile(SESSION);
    expect(out).toBeNull();
  });

  it('body NO json no rompe (devuelve null)', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true, status: 200, text: () => Promise.resolve('plain text'),
    });
    const out = await getMyGdProfile(SESSION);
    expect(out).toBeNull();
  });
});
