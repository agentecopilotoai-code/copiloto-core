/**
 * Cobertura completa del cliente HTTP transversal `coreApi.js`.
 *
 * Mockea `globalThis.fetch` y ejercita CADA helper exportado al menos una
 * vez (positive path + branches negativos del helper genérico `request()`).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  activateSupportMode,
  assignCapabilityToRole,
  createPlatformCapability,
  createPlatformFeatureFlag,
  createPlatformRole,
  createTenant,
  createTenantAsPlatformOwner,
  deactivateSupportMode,
  deletePlatformFeatureFlag,
  deletePlatformRole,
  getMyNotifications,
  getMyPreferences,
  getMyProfile,
  getPlatformBillingMrr,
  getPlatformFeatureFlags,
  getPlatformIncidents,
  getPlatformOutboundDlq,
  getPlatformRunbook,
  getPlatformRunbooks,
  getSystemHealth,
  getTenant,
  inviteTenantMember,
  listAIProviders,
  listFleetTenants,
  listMySessions,
  listMyTenants,
  listPlatformCapabilities,
  listPlatformRoles,
  listRoleCapabilities,
  listTenantMembers,
  listTenantModules,
  patchMyNotifications,
  patchMyPreferences,
  patchMyProfile,
  patchPlatformFeatureFlag,
  patchPlatformRole,
  patchTenantStatus,
  removeTenantMember,
  request,
  retryPlatformOutboundDlq,
  revokeCapabilityFromRole,
  revokeMySession,
  testAIProvider,
  updateAIProvider,
  updateTenant,
  updateTenantMemberRole,
  updateTenantModule,
} from './coreApi.js';

const SESSION = {
  accessToken: 'tk',
  api: { baseUrl: '/admin/api/core/v1' },
};
const TENANT_ID = 't-1';

function mockJson(payload, { ok = true, status = 200, statusText = 'OK' } = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  });
}

function mockEmpty204() {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 204,
    json: async () => null,
  });
}

function lastUrl() {
  const args = globalThis.fetch.mock.calls.at(-1);
  return args?.[0] ?? '';
}

function lastInit() {
  const args = globalThis.fetch.mock.calls.at(-1);
  return args?.[1] ?? {};
}

function bodyOf() {
  const body = lastInit().body;
  return body ? JSON.parse(body) : undefined;
}

beforeEach(() => {
  mockJson({});
});

afterEach(() => {
  globalThis.fetch = undefined;
});

// --------------------------------------------------------------------------
// request() — paths positivos y negativos del helper genérico.
// --------------------------------------------------------------------------
describe('request()', () => {
  it('GET sin body manda accept + sin content-type', async () => {
    await request('/health', { session: SESSION });
    expect(lastInit().method).toBe('GET');
    expect(lastInit().headers.accept).toBe('application/json');
    expect(lastInit().headers['content-type']).toBeUndefined();
  });

  it('agrega Authorization y X-Tenant-Id cuando vienen', async () => {
    await request('/x', { session: SESSION, tenantId: TENANT_ID });
    expect(lastInit().headers.authorization).toBe('Bearer tk');
    expect(lastInit().headers['X-Tenant-Id']).toBe(TENANT_ID);
  });

  it('POST con body serializa JSON y setea content-type', async () => {
    await request('/x', { method: 'POST', session: SESSION, body: { a: 1 } });
    expect(lastInit().method).toBe('POST');
    expect(lastInit().headers['content-type']).toBe('application/json');
    expect(bodyOf()).toEqual({ a: 1 });
  });

  it('204 devuelve null', async () => {
    mockEmpty204();
    const out = await request('/x', { method: 'DELETE', session: SESSION });
    expect(out).toBeNull();
  });

  it('error con detail string usa ese mensaje', async () => {
    mockJson({ detail: 'nope' }, { ok: false, status: 403 });
    await expect(request('/x', { session: SESSION })).rejects.toThrow('nope');
  });

  it('error con detail pydantic-array lo formatea', async () => {
    mockJson(
      {
        detail: [
          { loc: ['body', 'name'], msg: 'required' },
          { loc: ['body', 'email'], msg: 'invalid' },
        ],
      },
      { ok: false, status: 422 },
    );
    await expect(request('/x', { session: SESSION })).rejects.toThrow(
      'name: required · email: invalid',
    );
  });

  it('error con detail object usa detail.message', async () => {
    mockJson({ detail: { message: 'boom' } }, { ok: false, status: 500 });
    await expect(request('/x', { session: SESSION })).rejects.toThrow('boom');
  });

  it('error con payload completo serializa JSON.stringify', async () => {
    mockJson({ err: 'nope' }, { ok: false, status: 500 });
    await expect(request('/x', { session: SESSION })).rejects.toThrow(/"err":"nope"/);
  });

  it('error con JSON parse fail usa statusText', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Boom',
      json: async () => { throw new Error('not json'); },
    });
    await expect(request('/x', { session: SESSION })).rejects.toThrow('Boom');
  });

  it('error con statusText vacío usa HTTP <status>', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: '',
      json: async () => { throw new Error('not json'); },
    });
    await expect(request('/x', { session: SESSION })).rejects.toThrow('HTTP 500');
  });

  it('usa default baseUrl cuando session.api no está', async () => {
    await request('/x', { session: { accessToken: 'tk' } });
    expect(lastUrl()).toContain('/admin/api/core/v1/x');
  });
});

// --------------------------------------------------------------------------
// /me/* endpoints.
// --------------------------------------------------------------------------
describe('/me/* endpoints', () => {
  it('getMyProfile → GET /me/profile', async () => {
    await getMyProfile(SESSION);
    expect(lastUrl()).toContain('/me/profile');
  });

  it('patchMyProfile → PATCH', async () => {
    await patchMyProfile(SESSION, { display_name: 'X' });
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ display_name: 'X' });
  });

  it('getMyPreferences + patchMyPreferences', async () => {
    await getMyPreferences(SESSION);
    expect(lastUrl()).toContain('/me/preferences');
    await patchMyPreferences(SESSION, { theme_override: 'dark' });
    expect(lastInit().method).toBe('PATCH');
  });

  it('getMyNotifications + patchMyNotifications wrappea en notification_matrix', async () => {
    await getMyNotifications(SESSION);
    expect(lastUrl()).toContain('/me/notifications');
    await patchMyNotifications(SESSION, { ev1: { email: true } });
    expect(bodyOf()).toEqual({ notification_matrix: { ev1: { email: true } } });
  });

  it('listMySessions / revokeMySession', async () => {
    await listMySessions(SESSION);
    expect(lastUrl()).toContain('/me/sessions');
    await revokeMySession(SESSION, 'sess-1');
    expect(lastInit().method).toBe('DELETE');
    expect(lastUrl()).toContain('/me/sessions/sess-1');
  });

  it('listMyTenants → /me/tenants', async () => {
    await listMyTenants(SESSION);
    expect(lastUrl()).toContain('/me/tenants');
  });
});

// --------------------------------------------------------------------------
// tenant-signup + /tenants/*.
// --------------------------------------------------------------------------
describe('tenants endpoints', () => {
  it('createTenant → POST /tenant-signup', async () => {
    await createTenant(SESSION, { slug: 'acme' });
    expect(lastUrl()).toContain('/tenant-signup');
    expect(lastInit().method).toBe('POST');
  });

  it('createTenantAsPlatformOwner → POST /tenants', async () => {
    await createTenantAsPlatformOwner(SESSION, { slug: 'acme' });
    expect(lastUrl()).toMatch(/\/tenants$/);
    expect(lastInit().method).toBe('POST');
  });

  it('listFleetTenants sin filtros omite query', async () => {
    await listFleetTenants(SESSION);
    expect(lastUrl()).toMatch(/\/tenants$/);
  });

  it('listFleetTenants con todos los filtros', async () => {
    await listFleetTenants(SESSION, {
      status: 'active',
      country: 'CO',
      vertical: 'spa',
      search: 'acme',
      limit: 50,
      offset: 10,
    });
    expect(lastUrl()).toContain('status=active');
    expect(lastUrl()).toContain('country_code=CO');
    expect(lastUrl()).toContain('vertical_code=spa');
    expect(lastUrl()).toContain('search=acme');
    expect(lastUrl()).toContain('limit=50');
    expect(lastUrl()).toContain('offset=10');
  });

  it('getTenant', async () => {
    await getTenant(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}`);
  });

  it('updateTenant + patchTenantStatus', async () => {
    await updateTenant(SESSION, TENANT_ID, { display_name: 'X' });
    expect(lastInit().method).toBe('PATCH');
    await patchTenantStatus(SESSION, TENANT_ID, 'suspended');
    expect(lastUrl()).toContain('/status');
    expect(bodyOf()).toEqual({ status: 'suspended' });
  });
});

// --------------------------------------------------------------------------
// Tenant members.
// --------------------------------------------------------------------------
describe('members endpoints', () => {
  it('listTenantMembers / inviteTenantMember', async () => {
    await listTenantMembers(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}/members`);
    await inviteTenantMember(SESSION, TENANT_ID, { email: 'a@b.co' });
    expect(lastInit().method).toBe('POST');
  });

  it('updateTenantMemberRole / removeTenantMember', async () => {
    await updateTenantMemberRole(SESSION, TENANT_ID, 'u-1', 'admin');
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ role: 'admin' });
    await removeTenantMember(SESSION, TENANT_ID, 'u-1');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// /platform/* endpoints.
// --------------------------------------------------------------------------
describe('platform/* endpoints', () => {
  it('getSystemHealth, getPlatformBillingMrr', async () => {
    await getSystemHealth(SESSION);
    expect(lastUrl()).toContain('/platform/metrics/health');
    await getPlatformBillingMrr(SESSION);
    expect(lastUrl()).toContain('/platform/billing/mrr');
  });

  it('getPlatformIncidents sin filtros + con filtros', async () => {
    await getPlatformIncidents(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/incidents$/);
    await getPlatformIncidents(SESSION, { status: 'open', limit: 20 });
    expect(lastUrl()).toContain('status=open');
    expect(lastUrl()).toContain('limit=20');
  });

  it('getPlatformOutboundDlq / retryPlatformOutboundDlq', async () => {
    await getPlatformOutboundDlq(SESSION);
    expect(lastUrl()).toContain('/platform/outbound-dlq');
    await retryPlatformOutboundDlq(SESSION, { ids: [1, 2] });
    expect(lastInit().method).toBe('POST');
    expect(bodyOf()).toEqual({ ids: [1, 2] });
  });

  it('getPlatformRunbooks + getPlatformRunbook con slug encodeado', async () => {
    await getPlatformRunbooks(SESSION);
    expect(lastUrl()).toContain('/platform/runbooks');
    await getPlatformRunbook(SESSION, 'my slug/with chars');
    expect(lastUrl()).toContain(encodeURIComponent('my slug/with chars'));
  });
});

// --------------------------------------------------------------------------
// Feature flags.
// --------------------------------------------------------------------------
describe('feature flags CRUD', () => {
  it('getPlatformFeatureFlags / createPlatformFeatureFlag', async () => {
    await getPlatformFeatureFlags(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/feature-flags$/);
    await createPlatformFeatureFlag(SESSION, { key: 'k', enabled: true });
    expect(lastInit().method).toBe('POST');
  });

  it('patchPlatformFeatureFlag / deletePlatformFeatureFlag', async () => {
    await patchPlatformFeatureFlag(SESSION, 'k', { enabled: false });
    expect(lastUrl()).toContain('/platform/feature-flags/k');
    expect(lastInit().method).toBe('PATCH');
    await deletePlatformFeatureFlag(SESSION, 'k');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// AI providers.
// --------------------------------------------------------------------------
describe('AI providers', () => {
  it('listAIProviders / updateAIProvider / testAIProvider', async () => {
    await listAIProviders(SESSION);
    expect(lastUrl()).toContain('/platform/ai-providers');
    await updateAIProvider(SESSION, 'llm', { provider: 'openai' });
    expect(lastUrl()).toContain('/platform/ai-providers/llm');
    expect(lastInit().method).toBe('PATCH');
    await testAIProvider(SESSION, 'llm', { prompt: 'hi' });
    expect(lastUrl()).toContain('/platform/ai-providers/llm/test');
    expect(lastInit().method).toBe('POST');
  });
});

// --------------------------------------------------------------------------
// Tenant modules.
// --------------------------------------------------------------------------
describe('tenant modules', () => {
  it('listTenantModules sin filtros / con filtros', async () => {
    await listTenantModules(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/tenant-modules$/);
    await listTenantModules(SESSION, {
      module: 'mod',
      enabled: true,
      tenantSearch: 'acme',
    });
    expect(lastUrl()).toContain('module=mod');
    expect(lastUrl()).toContain('enabled=true');
    expect(lastUrl()).toContain('tenant_search=acme');
  });

  it('updateTenantModule arma body solo con campos provistos', async () => {
    await updateTenantModule(SESSION, TENANT_ID, 'mod', { enabled: true });
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ enabled: true });
    await updateTenantModule(SESSION, TENANT_ID, 'mod', {
      enabled: false,
      plan: 'pro',
      notes: 'hola',
    });
    expect(bodyOf()).toEqual({ enabled: false, plan: 'pro', notes: 'hola' });
  });
});

// --------------------------------------------------------------------------
// Roles & Capabilities CRUD (Fase 2).
// --------------------------------------------------------------------------
describe('roles & capabilities', () => {
  it('listPlatformRoles / createPlatformRole / patchPlatformRole / deletePlatformRole', async () => {
    await listPlatformRoles(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/roles$/);
    await createPlatformRole(SESSION, { code: 'r1' });
    expect(lastInit().method).toBe('POST');
    await patchPlatformRole(SESSION, 'r1', { label: 'R1' });
    expect(lastInit().method).toBe('PATCH');
    await deletePlatformRole(SESSION, 'r1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('listPlatformCapabilities / createPlatformCapability', async () => {
    await listPlatformCapabilities(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/capabilities$/);
    await createPlatformCapability(SESSION, { code: 'team.read' });
    expect(lastInit().method).toBe('POST');
  });

  it('listRoleCapabilities / assignCapabilityToRole / revokeCapabilityFromRole', async () => {
    await listRoleCapabilities(SESSION, 'r1');
    expect(lastUrl()).toContain('/platform/roles/r1/capabilities');
    await assignCapabilityToRole(SESSION, 'r1', 'team.read', 'RW');
    expect(lastInit().method).toBe('PUT');
    expect(bodyOf()).toEqual({ access_level: 'RW' });
    await revokeCapabilityFromRole(SESSION, 'r1', 'team.read');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Support mode.
// --------------------------------------------------------------------------
describe('support mode', () => {
  it('activateSupportMode / deactivateSupportMode', async () => {
    await activateSupportMode(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/me/support-mode/${TENANT_ID}`);
    expect(lastInit().method).toBe('POST');
    await deactivateSupportMode(SESSION, TENANT_ID);
    expect(lastInit().method).toBe('DELETE');
  });
});
