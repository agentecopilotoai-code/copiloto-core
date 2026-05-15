/**
 * UI-012-FU: ensure ``uploadTenantBrandLogo`` POSTs multipart/form-data
 * to the new ``/tenants/{id}/branding/logo`` endpoint. Static-style
 * test — verifies the fetch contract without spinning up the real
 * backend.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getMyNotifications,
  getMyPreferences,
  getMyProfile,
  listMySessions,
  patchMyNotifications,
  patchMyPreferences,
  patchMyProfile,
  revokeMySession,
  uploadTenantBrandLogo,
} from './coreApi.js';

const TENANT_ID = 'tenant-abc';
const SESSION = { accessToken: 'tk', api: { baseUrl: '/admin/api/core/v1' } };

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ brand_logo_url: 'https://cdn.example/logo.png' }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('uploadTenantBrandLogo', () => {
  it('POSTs FormData with the ``file`` field to /tenants/:id/branding/logo', async () => {
    const file = new File(['fake'], 'logo.png', { type: 'image/png' });

    const result = await uploadTenantBrandLogo(SESSION, TENANT_ID, file);

    expect(result).toEqual({ brand_logo_url: 'https://cdn.example/logo.png' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toContain(`/tenants/${TENANT_ID}/branding/logo`);
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get('file')).toBe(file);

    // Multipart upload must NOT set content-type (browser appends the boundary).
    const headers = init.headers || {};
    expect(headers['content-type']).toBeUndefined();
    expect(headers['Content-Type']).toBeUndefined();
    // Auth header is still required.
    expect(headers.authorization).toBe('Bearer tk');
    expect(headers['X-Tenant-Id']).toBe(TENANT_ID);
  });

  it('surfaces server errors as Error.message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'mime type image/svg+xml not allowed for image' }),
    });

    const file = new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' });

    await expect(uploadTenantBrandLogo(SESSION, TENANT_ID, file)).rejects.toThrow(
      /mime type image\/svg\+xml not allowed/,
    );
  });
});

// UI-016.7-FU — verify the `/me/*` helpers hit the right paths/methods.
describe('coreApi /me/* helpers (UI-016.7-FU)', () => {
  function mockJsonResponse(body = {}) {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => body,
    });
  }

  it('getMyProfile -> GET /me/profile', async () => {
    mockJsonResponse({ user_id: 'u-1' });
    await getMyProfile(SESSION);
    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('/me/profile');
    expect(init.method || 'GET').toBe('GET');
    expect(init.headers.authorization).toBe('Bearer tk');
  });

  it('patchMyProfile -> PATCH /me/profile with JSON body', async () => {
    mockJsonResponse({ user_id: 'u-1' });
    await patchMyProfile(SESSION, { display_name: 'Camila' });
    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('/me/profile');
    expect(init.method).toBe('PATCH');
    expect(init.headers['content-type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ display_name: 'Camila' });
  });

  it('getMyPreferences -> GET /me/preferences', async () => {
    mockJsonResponse({ theme_override: 'dark' });
    await getMyPreferences(SESSION);
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/me/preferences');
  });

  it('patchMyPreferences -> PATCH /me/preferences', async () => {
    mockJsonResponse({ theme_override: 'light' });
    await patchMyPreferences(SESSION, { theme_override: 'light' });
    const [, init] = globalThis.fetch.mock.calls[0];
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ theme_override: 'light' });
  });

  it('getMyNotifications -> GET /me/notifications', async () => {
    mockJsonResponse({ notification_matrix: {} });
    await getMyNotifications(SESSION);
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/me/notifications');
  });

  it('patchMyNotifications -> wraps matrix in notification_matrix key', async () => {
    mockJsonResponse({ notification_matrix: { daily_digest: { email: true } } });
    await patchMyNotifications(SESSION, { daily_digest: { email: true } });
    const [, init] = globalThis.fetch.mock.calls[0];
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({
      notification_matrix: { daily_digest: { email: true } },
    });
  });

  it('listMySessions -> GET /me/sessions', async () => {
    mockJsonResponse({ sessions: [] });
    await listMySessions(SESSION);
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/me/sessions');
  });

  it('revokeMySession -> DELETE /me/sessions/{sid} with url-encoded id', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => null,
    });
    await revokeMySession(SESSION, 'current');
    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('/me/sessions/current');
    expect(init.method).toBe('DELETE');
  });
});
