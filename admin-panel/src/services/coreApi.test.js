/**
 * UI-012-FU: ensure ``uploadTenantBrandLogo`` POSTs multipart/form-data
 * to the new ``/tenants/{id}/branding/logo`` endpoint. Static-style
 * test — verifies the fetch contract without spinning up the real
 * backend.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { uploadTenantBrandLogo } from './coreApi.js';

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
