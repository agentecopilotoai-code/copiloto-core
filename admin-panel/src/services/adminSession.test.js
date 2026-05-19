/**
 * Cover adminSession.js — currently 29.41%.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminPath, fetchAdminSession } from './adminSession.js';


describe('adminSession', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('adminPath returns prefixed path (no env origin)', () => {
    // Without backendOrigin set, the prefix is ''
    const out = adminPath('/admin/login');
    expect(out).toContain('/admin/login');
  });

  it('fetchAdminSession returns null on 401', async () => {
    fetch.mockResolvedValueOnce({ status: 401, ok: false });
    const out = await fetchAdminSession();
    expect(out).toBeNull();
  });

  it('fetchAdminSession returns parsed JSON on 200', async () => {
    const payload = { sub: 'user1', roles: ['admin'] };
    fetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: () => Promise.resolve(payload),
    });
    const out = await fetchAdminSession();
    expect(out).toEqual(payload);
  });

  it('fetchAdminSession throws on 500', async () => {
    fetch.mockResolvedValueOnce({ status: 500, ok: false });
    await expect(fetchAdminSession()).rejects.toThrow(/sesión/i);
  });

  it('fetchAdminSession throws on 403', async () => {
    fetch.mockResolvedValueOnce({ status: 403, ok: false });
    await expect(fetchAdminSession()).rejects.toThrow();
  });

  it('fetchAdminSession sends credentials=include', async () => {
    fetch.mockResolvedValueOnce({
      status: 200, ok: true, json: () => Promise.resolve({}),
    });
    await fetchAdminSession();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/admin/api/session'),
      expect.objectContaining({ credentials: 'include' }),
    );
  });
});
