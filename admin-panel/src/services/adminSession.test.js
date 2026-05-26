/**
 * Cover adminSession.js — currently 29.41%.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminPath, fetchAdminSession, SESSION_UNAUTHORIZED } from './adminSession.js';


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

  // M46 — 401 ahora devuelve {unauthorized: SESSION_UNAUTHORIZED, reason: ...}
  // en lugar de null. Esto permite distinguir "user nuevo" de "sesión zombie".
  it('fetchAdminSession returns unauthorized+reason on 401 with reason in body', async () => {
    fetch.mockResolvedValueOnce({
      status: 401, ok: false,
      json: () => Promise.resolve({ authenticated: false, reason: 'session_expired' }),
    });
    const out = await fetchAdminSession();
    expect(out).toEqual({ unauthorized: SESSION_UNAUTHORIZED, reason: 'session_expired' });
  });

  it('fetchAdminSession returns reason=no_session for plain 401', async () => {
    fetch.mockResolvedValueOnce({
      status: 401, ok: false,
      json: () => Promise.resolve({ authenticated: false, reason: 'no_session' }),
    });
    const out = await fetchAdminSession();
    expect(out.unauthorized).toBe(SESSION_UNAUTHORIZED);
    expect(out.reason).toBe('no_session');
  });

  it('fetchAdminSession returns reason=unknown when 401 body is not JSON', async () => {
    fetch.mockResolvedValueOnce({
      status: 401, ok: false,
      json: () => Promise.reject(new Error('not json')),
    });
    const out = await fetchAdminSession();
    expect(out.unauthorized).toBe(SESSION_UNAUTHORIZED);
    expect(out.reason).toBe('unknown');
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
