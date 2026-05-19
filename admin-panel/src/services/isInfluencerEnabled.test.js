/**
 * UI-INFLU-002 — Tests del helper `isInfluencerEnabled`.
 *
 * El helper traduce la respuesta del backend (TASK-INFLU-001) a un boolean
 * que el shell del módulo usa para decidir si renderizar el módulo o el
 * banner "Módulo no habilitado":
 *
 *   - 200 → true  (módulo activo).
 *   - 404 → false (módulo no activo — decisión D2 del backlog).
 *   - cualquier otro error (401/403/5xx) → propagado al caller.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isInfluencerEnabled } from './coreApi.js';

const SESSION = { token: 'fake-jwt' };
const TENANT_ID = '11111111-2222-3333-4444-555555555555';

describe('UI-INFLU-002 — isInfluencerEnabled', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('retorna true cuando el backend responde 200', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ module: 'influencer', status: 'active' }),
    });
    const result = await isInfluencerEnabled(SESSION, TENANT_ID);
    expect(result).toBe(true);
  });

  it('retorna false cuando el backend responde 404 (módulo no activo)', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: () => Promise.resolve({ detail: 'Not Found' }),
    });
    const result = await isInfluencerEnabled(SESSION, TENANT_ID);
    expect(result).toBe(false);
  });

  it('propaga errores distintos de 404 (401/403/5xx)', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: () => Promise.resolve({ detail: 'boom' }),
    });
    await expect(isInfluencerEnabled(SESSION, TENANT_ID)).rejects.toThrow();
  });

  it('llama el endpoint correcto con headers de tenant', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ module: 'influencer', status: 'active' }),
    });
    await isInfluencerEnabled(SESSION, TENANT_ID);
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toMatch(/\/influencer\/_health/);
    expect(init.headers['X-Tenant-Id']).toBe(TENANT_ID);
  });
});
