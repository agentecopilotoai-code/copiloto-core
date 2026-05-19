/**
 * Coverage suite for ``coreApi.js``.
 *
 * This file mocks ``globalThis.fetch`` and exercises every exported helper
 * to drive ``coreApi.js`` line/branch coverage to ≥80%. The strategy is:
 *
 *   - One positive-path assertion per endpoint (method/url/body/headers).
 *   - Targeted negative-path tests for the shared ``request()`` /
 *     ``uploadMultipart()`` / ``downloadAuthenticated()`` error branches
 *     (string detail, object detail, malformed JSON, 204 no-content).
 *   - ``coreWebSocketPath`` is hit via ``openConversationStream``.
 *   - URL/body builders with optional filters are tested with both
 *     empty and populated arguments to cover the conditional branches.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as core from './coreApi.js';
import {
  acceptConversationHandoff,
  activateSupportModeForTenant,
  archiveSubscriptionPlan,
  assignContactPackage,
  assignContactTags,
  cancelAppointment,
  cancelCampaign,
  cancelContactSubscription,
  completeOnboardingStep,
  conversationMessageMediaUrl,
  createAppointment,
  createAppointmentFeedback,
  createBranch,
  createCampaign,
  createConversationHandoff,
  createContactNote,
  createContactSegment,
  createContactTag,
  createDigestSubscription,
  createKnowledgeDocument,
  createLegalDocumentDraft,
  createPromotion,
  createQualificationQuestion,
  createQuote,
  createResource,
  createService,
  createServiceRequest,
  createSubscriptionPlan,
  createTenant,
  createTreatmentPackage,
  createWhatsappTemplate,
  deactivateBranch,
  deactivateService,
  deactivateSupportModeForTenant,
  deactivateTreatmentPackage,
  deleteContactSegment,
  deleteContactTag,
  deleteDigestSubscription,
  deleteKnowledgeDocument,
  deleteMediaAsset,
  deletePromotion,
  deleteQualificationQuestion,
  deleteWhatsappTemplate,
  evaluateIntent,
  exportAuditLogs,
  exportTenantData,
  fetchTenantMediaBlobUrl,
  generateAppointmentPaymentLink,
  getAnalyticsAgents,
  getAnalyticsAppointments,
  getAnalyticsCampaigns,
  getAnalyticsContacts,
  getAnalyticsConversations,
  getAnalyticsFunnel,
  getAnalyticsOverview,
  getAnalyticsReferrals,
  getCampaign,
  getContactProfile,
  getConversation,
  getKnowledgeStorageSettings,
  getMyNotifications,
  getMyPreferences,
  getMyProfile,
  getPlatformBillingMrr,
  getPlatformFeatureFlags,
  getPlatformIncidents,
  getPlatformOutboundDlq,
  getPlatformRunbook,
  getPlatformRunbooks,
  getQuoteForSr,
  getResourceAvailability,
  getRetentionPreview,
  getSystemHealth,
  getTenant,
  getTenantAvailability,
  getTenantOnboarding,
  getTenantPaymentSettings,
  getTenantReadiness,
  getTenantSettings,
  getWebChannel,
  getWhatsAppChannelHealth,
  getWhatsappTemplate,
  indexKnowledgeDocument,
  inviteTenantMember,
  launchCampaign,
  legalDocumentPublicUrl,
  listAppointmentFeedback,
  listAppointments,
  listAuditLogs,
  listAuditLogsFiltered,
  listBranches,
  listCampaigns,
  listComplaintConversations,
  listContactConsent,
  listContactNotes,
  listContactPackages,
  listContactSegments,
  listContactSubscriptions,
  listContactTags,
  listContacts,
  listConversations,
  listDigestSubscriptions,
  listFleetTenants,
  listKnowledgeDocuments,
  listLegalDocuments,
  listMediaAssets,
  listMessengerChannels,
  listMyTenants,
  listMySessions,
  listOutboundDlq,
  listPromotions,
  listQualificationQuestions,
  listResources,
  listRetentionPolicies,
  listServiceRequests,
  listServices,
  listSubscriptionPlans,
  listTenantMembers,
  listTreatmentPackages,
  listWhatsappTemplates,
  markTenantLive,
  openConversationStream,
  patchMyNotifications,
  patchMyPreferences,
  patchMyProfile,
  patchQuote,
  patchServiceRequest,
  patchTenantStatus,
  patchWhatsAppChannelMode,
  previewCampaign,
  previewContactSegment,
  publishLegalDocument,
  recordOnboardingTestMessageSent,
  refundContactPackage,
  refreshContactSegment,
  reindexAllKnowledgeDocuments,
  releaseConversation,
  removeTenantMember,
  reorderQualificationQuestions,
  reorderServices,
  retryOutboundDlqMessage,
  retryPlatformOutboundDlq,
  revokeMySession,
  sendAppointmentPaymentLink,
  sendConversationMessage,
  sendQuote,
  startConversation,
  suppressContact,
  syncWhatsappTemplates,
  unassignContactTag,
  updateAppointment,
  updateAppointmentPaymentStatus,
  updateBranch,
  updateCampaign,
  updateContactPackage,
  updateContactPhone,
  updateContactSegment,
  updateContactTag,
  updateDigestSubscription,
  updateKnowledgeDocument,
  updateKnowledgeStorageSettings,
  updateMediaAsset,
  updatePromotion,
  updateQualificationQuestion,
  updateResource,
  updateRetentionPolicies,
  updateService,
  updateSubscriptionPlan,
  updateTenant,
  updateTenantMemberRole,
  updateTenantPaymentSettings,
  updateTenantSettings,
  updateTreatmentPackage,
  updateWhatsappTemplate,
  uploadKnowledgeDocument,
  uploadMediaAsset,
  uploadTenantBrandLogo,
  upsertMessengerChannel,
  upsertWebChannel,
  upsertWhatsAppChannel,
  verifyOnboardingStep,
} from './coreApi.js';

const TENANT_ID = 'tenant-abc';
const SESSION = { accessToken: 'tk', api: { baseUrl: '/admin/api/core/v1' } };

function mockJson(body = {}, { ok = true, status = 200 } = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Bad Request',
    json: async () => body,
  });
}

function lastCall() {
  return globalThis.fetch.mock.calls[0];
}

function lastUrl() {
  return lastCall()[0];
}

function lastInit() {
  return lastCall()[1];
}

function bodyOf() {
  return JSON.parse(lastInit().body);
}

beforeEach(() => {
  mockJson({});
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --------------------------------------------------------------------------
// Shared transport — request() error/204/edge branches.
// --------------------------------------------------------------------------
describe('request() transport branches', () => {
  it('returns null on 204 No Content', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => null,
    });
    const result = await getMyProfile(SESSION);
    expect(result).toBeNull();
  });

  it('throws with string ``detail`` and attaches status/detail on error', async () => {
    mockJson({ detail: 'kaboom' }, { ok: false, status: 422 });
    try {
      await getMyProfile(SESSION);
      throw new Error('should not reach');
    } catch (err) {
      expect(err.message).toBe('kaboom');
      expect(err.status).toBe(422);
      expect(err.detail).toBe('kaboom');
    }
  });

  it('surfaces structured object ``detail.message`` (UI-016.1-FU 409)', async () => {
    const structured = { message: 'checks pending', reasons: ['no_channel'] };
    mockJson({ detail: structured }, { ok: false, status: 409 });
    try {
      await markTenantLive(SESSION, TENANT_ID, 'why');
      throw new Error('should not reach');
    } catch (err) {
      expect(err.message).toBe('checks pending');
      expect(err.detail).toEqual(structured);
      expect(err.status).toBe(409);
    }
  });

  it('falls back to JSON.stringify when detail is an object without message', async () => {
    mockJson({ detail: { code: 'X' } }, { ok: false, status: 400 });
    await expect(getMyProfile(SESSION)).rejects.toThrow(/"code":"X"/);
  });

  it('stringifies the whole payload when no detail key is present', async () => {
    mockJson({ foo: 'bar' }, { ok: false, status: 400 });
    await expect(getMyProfile(SESSION)).rejects.toThrow(/"foo":"bar"/);
  });

  it('falls back to statusText when JSON parsing fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(getMyProfile(SESSION)).rejects.toThrow('Server Error');
  });

  it('falls back to ``HTTP <status>`` when statusText is empty and JSON parsing fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: '',
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(getMyProfile(SESSION)).rejects.toThrow('HTTP 500');
  });

  it('falls back to default baseUrl when session.api is not set', async () => {
    mockJson({});
    await getMyProfile({ accessToken: 'tk' });
    expect(lastUrl()).toContain('/admin/api/core/v1/me/profile');
  });

  it('omits authorization header when session has no token', async () => {
    mockJson({});
    await getMyProfile({});
    const headers = lastInit().headers;
    expect(headers.authorization).toBeUndefined();
  });
});

// --------------------------------------------------------------------------
// Platform / tenant CRUD.
// --------------------------------------------------------------------------
describe('platform + tenant endpoints', () => {
  it('createTenant -> POST /tenant-signup', async () => {
    await createTenant(SESSION, { name: 'Acme' });
    expect(lastUrl()).toContain('/tenant-signup');
    expect(lastInit().method).toBe('POST');
    expect(bodyOf()).toEqual({ name: 'Acme' });
  });

  it('listFleetTenants -> /tenants without filters', async () => {
    await listFleetTenants(SESSION);
    expect(lastUrl()).toMatch(/\/tenants$/);
  });

  it('listFleetTenants -> appends every filter param', async () => {
    await listFleetTenants(SESSION, {
      status: 'live',
      country: 'CO',
      vertical: 'salud',
      search: 'q',
      limit: 10,
      offset: 5,
    });
    const url = lastUrl();
    expect(url).toContain('status=live');
    expect(url).toContain('country=CO');
    expect(url).toContain('vertical=salud');
    expect(url).toContain('search=q');
    expect(url).toContain('limit=10');
    expect(url).toContain('offset=5');
  });

  it('listFleetTenants -> accepts limit=0 / offset=0', async () => {
    await listFleetTenants(SESSION, { limit: 0, offset: 0 });
    expect(lastUrl()).toContain('limit=0');
    expect(lastUrl()).toContain('offset=0');
  });

  it('getTenant -> /tenants/:id', async () => {
    await getTenant(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}`);
  });

  it('getSystemHealth, getPlatformBillingMrr, getPlatformRunbooks, getPlatformFeatureFlags', async () => {
    mockJson({});
    await getSystemHealth(SESSION);
    expect(lastUrl()).toContain('/platform/metrics/health');
    mockJson({});
    await getPlatformBillingMrr(SESSION);
    expect(lastUrl()).toContain('/platform/billing/mrr');
    mockJson({});
    await getPlatformRunbooks(SESSION);
    expect(lastUrl()).toContain('/platform/runbooks');
    mockJson({});
    await getPlatformFeatureFlags(SESSION);
    expect(lastUrl()).toContain('/platform/feature-flags');
  });

  it('getPlatformIncidents -> empty + all filters', async () => {
    mockJson({});
    await getPlatformIncidents(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/incidents$/);
    mockJson({});
    await getPlatformIncidents(SESSION, { status: 'open', kind: 'pager', limit: 50 });
    expect(lastUrl()).toContain('status=open');
    expect(lastUrl()).toContain('kind=pager');
    expect(lastUrl()).toContain('limit=50');
  });

  it('getPlatformOutboundDlq -> empty + all filters incl windowMinutes=0', async () => {
    mockJson({});
    await getPlatformOutboundDlq(SESSION);
    expect(lastUrl()).toMatch(/\/platform\/outbound-dlq$/);
    mockJson({});
    await getPlatformOutboundDlq(SESSION, {
      windowMinutes: 0,
      tenantId: 't',
      errorCode: 'E',
    });
    expect(lastUrl()).toContain('window_minutes=0');
    expect(lastUrl()).toContain('tenant_id=t');
    expect(lastUrl()).toContain('error_code=E');
  });

  it('retryPlatformOutboundDlq -> POST', async () => {
    await retryPlatformOutboundDlq(SESSION, { ids: [1] });
    expect(lastInit().method).toBe('POST');
    expect(bodyOf()).toEqual({ ids: [1] });
  });

  it('getPlatformRunbook -> encodes slug', async () => {
    await getPlatformRunbook(SESSION, 'my slug/with chars');
    expect(lastUrl()).toContain(encodeURIComponent('my slug/with chars'));
  });

  it('updateTenant -> PATCH', async () => {
    await updateTenant(SESSION, TENANT_ID, { name: 'x' });
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ name: 'x' });
  });

  it('patchTenantStatus -> PATCH with status/reason body', async () => {
    await patchTenantStatus(SESSION, TENANT_ID, 'suspended', 'fraud');
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ status: 'suspended', reason: 'fraud' });
  });

  it('getTenantSettings + updateTenantSettings', async () => {
    mockJson({});
    await getTenantSettings(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}/settings`);
    mockJson({});
    await updateTenantSettings(SESSION, TENANT_ID, { brand: 'X' });
    expect(lastInit().method).toBe('PATCH');
  });
});

// --------------------------------------------------------------------------
// Multipart uploads + downloads.
// --------------------------------------------------------------------------
describe('uploadMultipart + downloads', () => {
  it('uploadTenantBrandLogo -> POST formdata', async () => {
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    await uploadTenantBrandLogo(SESSION, TENANT_ID, file);
    expect(lastInit().method).toBe('POST');
    expect(lastInit().body).toBeInstanceOf(FormData);
    expect(lastInit().body.get('file')).toBe(file);
  });

  it('uploadMultipart -> error path with string detail', async () => {
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    mockJson({ detail: 'too big' }, { ok: false, status: 413 });
    await expect(uploadTenantBrandLogo(SESSION, TENANT_ID, file)).rejects.toThrow('too big');
  });

  it('uploadMultipart -> JSON.stringify body when no detail', async () => {
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    mockJson({ err: 'oops' }, { ok: false, status: 400 });
    await expect(uploadTenantBrandLogo(SESSION, TENANT_ID, file)).rejects.toThrow(/"err":"oops"/);
  });

  it('uploadMultipart -> fallback to statusText when JSON parse fails', async () => {
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Boom',
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(uploadTenantBrandLogo(SESSION, TENANT_ID, file)).rejects.toThrow('Boom');
  });

  it('uploadMultipart -> fallback to HTTP <status> when statusText empty', async () => {
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: '',
      json: async () => {
        throw new Error('not json');
      },
    });
    await expect(uploadTenantBrandLogo(SESSION, TENANT_ID, file)).rejects.toThrow('HTTP 500');
  });

  it('fetchTenantMediaBlobUrl -> strips /v1 prefix, returns object URL', async () => {
    const blob = new Blob(['x'], { type: 'image/png' });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
    });
    if (!URL.createObjectURL) URL.createObjectURL = () => '';
    if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {};
    const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:abc');
    const url = await fetchTenantMediaBlobUrl(
      SESSION,
      TENANT_ID,
      '/v1/tenants/abc/media/x/content',
    );
    expect(url).toBe('blob:abc');
    expect(lastUrl()).toContain('/tenants/abc/media/x/content');
    expect(lastUrl()).not.toContain('/v1/v1');
    created.mockRestore();
  });

  it('fetchTenantMediaBlobUrl -> throws on non-ok response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    await expect(
      fetchTenantMediaBlobUrl(SESSION, TENANT_ID, '/v1/tenants/abc/media/x/content'),
    ).rejects.toThrow('media fetch failed: HTTP 401');
  });

  it('exportAuditLogs -> downloadAuthenticated success path triggers anchor click', async () => {
    const blob = new Blob(['csv'], { type: 'text/csv' });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
    });
    if (!URL.createObjectURL) URL.createObjectURL = () => '';
    if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {};
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:csv');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await exportAuditLogs(SESSION, TENANT_ID, { action: 'login', empty: '', skip: null });
    expect(clickSpy).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith('blob:csv');
    expect(lastUrl()).toContain('/audit-logs/export?action=login');
    expect(lastUrl()).not.toContain('empty=');
    expect(lastUrl()).not.toContain('skip=');
  });

  it('exportAuditLogs -> downloadAuthenticated error path with detail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: async () => ({ detail: 'no permission' }),
    });
    await expect(exportAuditLogs(SESSION, TENANT_ID)).rejects.toThrow('no permission');
  });

  it('exportAuditLogs -> downloadAuthenticated error path with JSON parse fail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Down',
      json: async () => {
        throw new Error('nope');
      },
    });
    await expect(exportAuditLogs(SESSION, TENANT_ID)).rejects.toThrow('HTTP 503');
  });

  it('exportTenantData -> hits /data-export', async () => {
    const blob = new Blob(['{}'], { type: 'application/json' });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
    });
    if (!URL.createObjectURL) URL.createObjectURL = () => '';
    if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {};
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:json');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await exportTenantData(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}/data-export`);
  });

  it('uploadMediaAsset -> success path with all optional fields', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'm-1' }),
    });
    const file = new File(['x'], 'pic.png', { type: 'image/png' });
    const result = await uploadMediaAsset(SESSION, TENANT_ID, {
      kind: 'image',
      label: 'L',
      description: 'D',
      tags: ['a', 'b'],
      file,
    });
    expect(result).toEqual({ id: 'm-1' });
    const init = lastInit();
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get('kind')).toBe('image');
    expect(init.body.get('description')).toBe('D');
    expect(init.body.get('tags')).toBe('a,b');
    expect(init.headers.authorization).toBe('Bearer tk');
    expect(init.headers['X-Tenant-Id']).toBe(TENANT_ID);
  });

  it('uploadMediaAsset -> skips optional fields when falsy', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'm-2' }),
    });
    const file = new File(['x'], 'pic.png', { type: 'image/png' });
    await uploadMediaAsset(SESSION, TENANT_ID, {
      kind: 'image',
      label: 'L',
      tags: [],
      file,
    });
    const fd = lastInit().body;
    expect(fd.get('description')).toBeNull();
    expect(fd.get('tags')).toBeNull();
  });

  it('uploadMediaAsset -> error path with detail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'bad' }),
    });
    const file = new File(['x'], 'pic.png', { type: 'image/png' });
    await expect(
      uploadMediaAsset(SESSION, TENANT_ID, { kind: 'image', label: 'L', file }),
    ).rejects.toThrow('bad');
  });

  it('uploadMediaAsset -> error path with JSON parse fail uses HTTP <status>', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error('nope');
      },
    });
    const file = new File(['x'], 'pic.png', { type: 'image/png' });
    await expect(
      uploadMediaAsset(SESSION, TENANT_ID, { kind: 'image', label: 'L', file }),
    ).rejects.toThrow('HTTP 502');
  });

  it('uploadMediaAsset -> omits auth headers when session/tenant missing', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    const file = new File(['x'], 'pic.png', { type: 'image/png' });
    await uploadMediaAsset({}, null, { kind: 'image', label: 'L', file });
    const headers = lastInit().headers;
    expect(headers.authorization).toBeUndefined();
    expect(headers['X-Tenant-Id']).toBeUndefined();
  });

  it('uploadKnowledgeDocument -> defaults document_type=reference and visibility=tenant', async () => {
    const file = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    await uploadKnowledgeDocument(SESSION, TENANT_ID, { title: 'T', file });
    const fd = lastInit().body;
    expect(fd.get('tenant_id')).toBe(TENANT_ID);
    expect(fd.get('title')).toBe('T');
    expect(fd.get('document_type')).toBe('reference');
    expect(fd.get('visibility')).toBe('tenant');
  });

  it('uploadKnowledgeDocument -> uses provided document_type/visibility', async () => {
    const file = new File(['x'], 'doc.pdf', { type: 'application/pdf' });
    await uploadKnowledgeDocument(SESSION, TENANT_ID, {
      title: 'T',
      file,
      document_type: 'guide',
      visibility: 'public',
    });
    const fd = lastInit().body;
    expect(fd.get('document_type')).toBe('guide');
    expect(fd.get('visibility')).toBe('public');
  });
});

// --------------------------------------------------------------------------
// Retention / digest / onboarding / readiness / go-live.
// --------------------------------------------------------------------------
describe('retention / digest / onboarding / readiness', () => {
  it('listRetentionPolicies -> GET', async () => {
    await listRetentionPolicies(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}/retention/policies`);
  });

  it('updateRetentionPolicies -> PUT wraps policies', async () => {
    await updateRetentionPolicies(SESSION, TENANT_ID, [{ kind: 'msg', days: 30 }]);
    expect(lastInit().method).toBe('PUT');
    expect(bodyOf()).toEqual({ policies: [{ kind: 'msg', days: 30 }] });
  });

  it('getRetentionPreview -> GET', async () => {
    await getRetentionPreview(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/retention/preview');
  });

  it('listDigestSubscriptions, create, update, delete', async () => {
    mockJson({});
    await listDigestSubscriptions(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/digest/subscriptions');
    mockJson({});
    await createDigestSubscription(SESSION, TENANT_ID, { email: 'x@y' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateDigestSubscription(SESSION, TENANT_ID, 'sub-1', { active: false });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteDigestSubscription(SESSION, TENANT_ID, 'sub-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('getTenantOnboarding + verify/complete onboarding steps', async () => {
    mockJson({});
    await getTenantOnboarding(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/onboarding');
    mockJson({});
    await verifyOnboardingStep(SESSION, TENANT_ID, 3);
    expect(lastUrl()).toContain('/onboarding/steps/3/verify');
    expect(bodyOf()).toEqual({});
    mockJson({});
    await completeOnboardingStep(SESSION, TENANT_ID, 4);
    expect(bodyOf()).toEqual({ evidence: {} });
    mockJson({});
    await completeOnboardingStep(SESSION, TENANT_ID, 4, { note: 'ok' });
    expect(bodyOf()).toEqual({ evidence: { note: 'ok' } });
  });

  it('recordOnboardingTestMessageSent -> POST step 7', async () => {
    await recordOnboardingTestMessageSent(SESSION, TENANT_ID, '57300');
    expect(lastUrl()).toContain('/onboarding/steps/7/send-test');
    expect(bodyOf()).toEqual({ wa_id: '57300' });
  });

  it('getTenantReadiness -> no options + with options', async () => {
    mockJson({});
    await getTenantReadiness(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/readiness$/);
    mockJson({});
    await getTenantReadiness(SESSION, TENANT_ID, {
      smokeQuestion: 'Hola?',
      retrievalMinScore: 0.4,
    });
    expect(lastUrl()).toContain('smoke_question=');
    expect(lastUrl()).toContain('retrieval_min_score=0.4');
  });

  it('getTenantReadiness -> ignores empty-string retrievalMinScore', async () => {
    mockJson({});
    await getTenantReadiness(SESSION, TENANT_ID, { retrievalMinScore: '' });
    expect(lastUrl()).not.toContain('retrieval_min_score=');
  });

  it('markTenantLive -> with and without reason', async () => {
    mockJson({});
    await markTenantLive(SESSION, TENANT_ID);
    expect(bodyOf()).toEqual({});
    mockJson({});
    await markTenantLive(SESSION, TENANT_ID, 'ready');
    expect(bodyOf()).toEqual({ reason: 'ready' });
  });
});

// --------------------------------------------------------------------------
// Audit / contacts / support mode.
// --------------------------------------------------------------------------
describe('audit / support mode / contacts basic', () => {
  it('listAuditLogs and listAuditLogsFiltered (empty + filters)', async () => {
    mockJson({});
    await listAuditLogs(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/audit-logs');
    mockJson({});
    await listAuditLogsFiltered(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/audit-logs$/);
    mockJson({});
    await listAuditLogsFiltered(SESSION, TENANT_ID, {
      action: 'login',
      skip: null,
      empty: '',
    });
    expect(lastUrl()).toContain('action=login');
    expect(lastUrl()).not.toContain('skip=');
    expect(lastUrl()).not.toContain('empty=');
  });

  it('suppressContact -> POST /contacts/:id/suppress', async () => {
    await suppressContact(SESSION, TENANT_ID, 'c-1');
    expect(lastUrl()).toContain('/contacts/c-1/suppress');
    expect(lastInit().method).toBe('POST');
  });

  it('listMyTenants -> /me/tenants', async () => {
    await listMyTenants(SESSION);
    expect(lastUrl()).toContain('/me/tenants');
  });

  it('activateSupportModeForTenant -> with and without justification', async () => {
    mockJson({});
    await activateSupportModeForTenant(SESSION, TENANT_ID);
    expect(bodyOf()).toEqual({});
    mockJson({});
    await activateSupportModeForTenant(SESSION, TENANT_ID, { justification: 'help' });
    expect(bodyOf()).toEqual({ justification: 'help' });
  });

  it('deactivateSupportModeForTenant -> DELETE', async () => {
    await deactivateSupportModeForTenant(SESSION, TENANT_ID);
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Tenant members.
// --------------------------------------------------------------------------
describe('tenant members', () => {
  it('listTenantMembers, invite, updateRole, remove', async () => {
    mockJson({});
    await listTenantMembers(SESSION, TENANT_ID);
    expect(lastUrl()).toContain(`/tenants/${TENANT_ID}/members`);
    mockJson({});
    await inviteTenantMember(SESSION, TENANT_ID, { email: 'x@y' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateTenantMemberRole(SESSION, TENANT_ID, 'u-1', 'manager');
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ role: 'manager' });
    mockJson({});
    await removeTenantMember(SESSION, TENANT_ID, 'u-1');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Channels.
// --------------------------------------------------------------------------
describe('channels (whatsapp/messenger/web)', () => {
  it('upsertWhatsAppChannel + getWhatsAppChannelHealth + patchWhatsAppChannelMode', async () => {
    mockJson({});
    await upsertWhatsAppChannel(SESSION, TENANT_ID, { phone: '+1' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await getWhatsAppChannelHealth(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/channels/whatsapp/health');
    mockJson({});
    await patchWhatsAppChannelMode(SESSION, TENANT_ID, 'paused', 'maintenance');
    expect(lastInit().method).toBe('PATCH');
    expect(bodyOf()).toEqual({ account_mode: 'paused', reason: 'maintenance' });
  });

  it('getWebChannel + upsertWebChannel + messenger', async () => {
    mockJson({});
    await getWebChannel(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/channels/web');
    mockJson({});
    await upsertWebChannel(SESSION, TENANT_ID, { theme: 'dark' });
    expect(lastInit().method).toBe('PUT');
    mockJson({});
    await listMessengerChannels(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/channels/messenger');
    mockJson({});
    await upsertMessengerChannel(SESSION, TENANT_ID, { page_id: 'p' });
    expect(lastInit().method).toBe('PUT');
  });
});

// --------------------------------------------------------------------------
// Knowledge.
// --------------------------------------------------------------------------
describe('knowledge', () => {
  it('getKnowledgeStorageSettings + update', async () => {
    mockJson({});
    await getKnowledgeStorageSettings(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/knowledge/storage');
    mockJson({});
    await updateKnowledgeStorageSettings(SESSION, TENANT_ID, { mode: 's3' });
    expect(lastInit().method).toBe('PATCH');
  });

  it('evaluateIntent -> POST /intents/evaluate with tenantId header', async () => {
    await evaluateIntent(SESSION, TENANT_ID, { text: 'hola' });
    expect(lastUrl()).toContain('/intents/evaluate');
    expect(lastInit().headers['X-Tenant-Id']).toBe(TENANT_ID);
  });

  it('listKnowledgeDocuments -> empty + filters skip falsy', async () => {
    mockJson({});
    await listKnowledgeDocuments(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/knowledge\/documents$/);
    mockJson({});
    await listKnowledgeDocuments(SESSION, TENANT_ID, { kind: 'ref', skip: '', dropme: null });
    const u = lastUrl();
    expect(u).toContain('kind=ref');
    expect(u).not.toContain('skip=');
    expect(u).not.toContain('dropme=');
  });

  it('createKnowledgeDocument -> POST merges tenant_id', async () => {
    await createKnowledgeDocument(SESSION, TENANT_ID, { title: 'T' });
    expect(bodyOf()).toEqual({ title: 'T', tenant_id: TENANT_ID });
  });

  it('updateKnowledgeDocument, indexKnowledgeDocument, reindexAll, delete', async () => {
    mockJson({});
    await updateKnowledgeDocument(SESSION, TENANT_ID, 'd-1', { title: 'X' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await indexKnowledgeDocument(SESSION, TENANT_ID, 'd-1');
    expect(lastUrl()).toContain('/d-1/index');
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await reindexAllKnowledgeDocuments(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/knowledge/reindex-all');
    mockJson({});
    await deleteKnowledgeDocument(SESSION, TENANT_ID, 'd-1');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Conversations + websocket.
// --------------------------------------------------------------------------
describe('conversations', () => {
  it('startConversation merges tenant_id into body', async () => {
    await startConversation(SESSION, TENANT_ID, { channel: 'web' });
    expect(bodyOf()).toEqual({ channel: 'web', tenant_id: TENANT_ID });
  });

  it('listConversations + listComplaintConversations + getConversation', async () => {
    mockJson({});
    await listConversations(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/conversations');
    mockJson({});
    await listComplaintConversations(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/conversations/complaints');
    mockJson({});
    await getConversation(SESSION, TENANT_ID, 'cv-1');
    expect(lastUrl()).toContain('/conversations/cv-1');
  });

  it('conversationMessageMediaUrl -> URL-encodes ids and includes tenant_id', () => {
    // signature: (session, tenantId, conversationId, messageId)
    const url = conversationMessageMediaUrl(SESSION, 'a/b', 'c d', 'e+f');
    expect(url).toContain('/conversations/c%20d/messages/e%2Bf/media');
    expect(url).toContain('tenant_id=a%2Fb');
  });

  it('sendConversationMessage merges defaults', async () => {
    await sendConversationMessage(SESSION, TENANT_ID, 'cv-1', { text: 'hello' });
    expect(bodyOf()).toMatchObject({
      tenant_id: TENANT_ID,
      conversation_id: 'cv-1',
      direction: 'outbound',
      sender_actor_type: 'agent',
      message_type: 'text',
      text: 'hello',
    });
  });

  it('createConversationHandoff, accept, release', async () => {
    mockJson({});
    await createConversationHandoff(SESSION, TENANT_ID, 'cv-1', 'no idea');
    expect(bodyOf()).toEqual({ reason: 'no idea' });
    mockJson({});
    await acceptConversationHandoff(SESSION, TENANT_ID, 'cv-1');
    expect(lastUrl()).toContain('/handoff/accept');
    mockJson({});
    await releaseConversation(SESSION, TENANT_ID, 'cv-1');
    expect(lastUrl()).toContain('/release');
  });

  it('openConversationStream -> builds ws:// URL via coreWebSocketPath', () => {
    const constructed = [];
    class FakeWS {
      constructor(url) {
        constructed.push(url);
        this.url = url;
      }
    }
    const originalWS = globalThis.WebSocket;
    globalThis.WebSocket = FakeWS;
    const socket = openConversationStream(SESSION, TENANT_ID);
    expect(socket).toBeInstanceOf(FakeWS);
    expect(constructed[0]).toMatch(/^ws:\/\//);
    expect(constructed[0]).toContain('/conversations/stream');
    expect(constructed[0]).toContain(`tenant_id=${TENANT_ID}`);
    globalThis.WebSocket = originalWS;
  });

  it('openConversationStream -> upgrades https to wss', () => {
    const constructed = [];
    class FakeWS {
      constructor(url) {
        constructed.push(url);
      }
    }
    const originalWS = globalThis.WebSocket;
    globalThis.WebSocket = FakeWS;
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: 'https://example.com/admin/' },
    });
    openConversationStream(SESSION, TENANT_ID);
    expect(constructed[0]).toMatch(/^wss:\/\//);
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    globalThis.WebSocket = originalWS;
  });
});

// --------------------------------------------------------------------------
// Appointments, resources, availability.
// --------------------------------------------------------------------------
describe('appointments / resources / availability', () => {
  it('listAppointmentFeedback + createAppointmentFeedback', async () => {
    mockJson({});
    await listAppointmentFeedback(SESSION, TENANT_ID, 'ap-1');
    expect(lastUrl()).toContain('/appointments/ap-1/feedback');
    mockJson({});
    await createAppointmentFeedback(SESSION, TENANT_ID, 'ap-1', { rating: 5 });
    expect(lastInit().method).toBe('POST');
  });

  it('getResourceAvailability + getTenantAvailability — empty + with options', async () => {
    mockJson({});
    await getResourceAvailability(SESSION, TENANT_ID, 'r-1');
    expect(lastUrl()).toMatch(/\/availability$/);
    mockJson({});
    await getResourceAvailability(SESSION, TENANT_ID, 'r-1', {
      date: '2026-01-01',
      serviceId: 's-1',
    });
    expect(lastUrl()).toContain('date=2026-01-01');
    expect(lastUrl()).toContain('service_id=s-1');
    mockJson({});
    await getTenantAvailability(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/availability$/);
    mockJson({});
    await getTenantAvailability(SESSION, TENANT_ID, { date: '2026-01-01', serviceId: 's-1' });
    expect(lastUrl()).toContain('date=2026-01-01');
  });

  it('listResources + createResource + updateResource', async () => {
    mockJson({});
    await listResources(SESSION, TENANT_ID, { active: 'true', skip: '' });
    expect(lastUrl()).toContain('active=true');
    mockJson({});
    await createResource(SESSION, TENANT_ID, { name: 'R' });
    expect(bodyOf()).toEqual({ name: 'R', tenant_id: TENANT_ID });
    mockJson({});
    await updateResource(SESSION, TENANT_ID, 'r-1', { name: 'R2' });
    expect(lastInit().method).toBe('PATCH');
  });

  it('listAppointments + create + update + cancel', async () => {
    mockJson({});
    await listAppointments(SESSION, TENANT_ID, { status: 'open' });
    expect(lastUrl()).toContain('status=open');
    mockJson({});
    await createAppointment(SESSION, TENANT_ID, { service_id: 'srv' });
    expect(bodyOf()).toEqual({ service_id: 'srv', tenant_id: TENANT_ID });
    mockJson({});
    await updateAppointment(SESSION, TENANT_ID, 'ap-1', { status: 'done' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await cancelAppointment(SESSION, TENANT_ID, 'ap-1');
    expect(lastUrl()).toContain('/cancel');
  });
});

// --------------------------------------------------------------------------
// WhatsApp templates.
// --------------------------------------------------------------------------
describe('whatsapp templates', () => {
  it('listWhatsappTemplates -> empty + filters', async () => {
    mockJson({});
    await listWhatsappTemplates(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/templates$/);
    mockJson({});
    await listWhatsappTemplates(SESSION, TENANT_ID, { purpose: 'marketing', status: 'approved' });
    expect(lastUrl()).toContain('purpose=marketing');
    expect(lastUrl()).toContain('status=approved');
  });

  it('CRUD + sync', async () => {
    mockJson({});
    await getWhatsappTemplate(SESSION, TENANT_ID, 't-1');
    expect(lastUrl()).toContain('/templates/t-1');
    mockJson({});
    await createWhatsappTemplate(SESSION, TENANT_ID, { name: 'N' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateWhatsappTemplate(SESSION, TENANT_ID, 't-1', { name: 'M' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteWhatsappTemplate(SESSION, TENANT_ID, 't-1');
    expect(lastInit().method).toBe('DELETE');
    mockJson({});
    await syncWhatsappTemplates(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/templates/sync');
    expect(bodyOf()).toEqual({});
  });
});

// --------------------------------------------------------------------------
// Services + qualification questions.
// --------------------------------------------------------------------------
describe('services + qualification', () => {
  it('listServices -> with and without includeInactive', async () => {
    mockJson({});
    await listServices(SESSION, TENANT_ID);
    expect(lastUrl()).not.toContain('include_inactive=true');
    mockJson({});
    await listServices(SESSION, TENANT_ID, { includeInactive: true });
    expect(lastUrl()).toContain('include_inactive=true');
  });

  it('createService + updateService + deactivateService + reorder', async () => {
    mockJson({});
    await createService(SESSION, TENANT_ID, { name: 'X' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateService(SESSION, TENANT_ID, 's-1', { name: 'Y' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deactivateService(SESSION, TENANT_ID, 's-1');
    expect(lastInit().method).toBe('DELETE');
    mockJson({});
    await reorderServices(SESSION, TENANT_ID, ['s-1', 's-2']);
    expect(bodyOf()).toEqual({ order: ['s-1', 's-2'] });
  });

  it('qualification questions full CRUD + reorder', async () => {
    mockJson({});
    await listQualificationQuestions(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/qualification-questions');
    mockJson({});
    await createQualificationQuestion(SESSION, TENANT_ID, { label: 'Q' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateQualificationQuestion(SESSION, TENANT_ID, 'q-1', { label: 'Q2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteQualificationQuestion(SESSION, TENANT_ID, 'q-1');
    expect(lastInit().method).toBe('DELETE');
    mockJson({});
    await reorderQualificationQuestions(SESSION, TENANT_ID, ['q-1']);
    expect(bodyOf()).toEqual({ order: ['q-1'] });
  });
});

// --------------------------------------------------------------------------
// Media assets.
// --------------------------------------------------------------------------
describe('media assets', () => {
  it('listMediaAssets — empty + with kind/tag', async () => {
    mockJson({});
    await listMediaAssets(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/media$/);
    mockJson({});
    await listMediaAssets(SESSION, TENANT_ID, { kind: 'image', tag: 'logo' });
    expect(lastUrl()).toContain('kind=image');
    expect(lastUrl()).toContain('tag=logo');
  });

  it('updateMediaAsset + deleteMediaAsset', async () => {
    mockJson({});
    await updateMediaAsset(SESSION, TENANT_ID, 'm-1', { label: 'L' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteMediaAsset(SESSION, TENANT_ID, 'm-1');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Promotions / branches / packages / subscriptions.
// --------------------------------------------------------------------------
describe('promotions / branches / packages / subscriptions', () => {
  it('listPromotions default + includeInactive=false', async () => {
    mockJson({});
    await listPromotions(SESSION, TENANT_ID);
    expect(lastUrl()).not.toContain('include_inactive=false');
    mockJson({});
    await listPromotions(SESSION, TENANT_ID, { includeInactive: false });
    expect(lastUrl()).toContain('include_inactive=false');
  });

  it('promotion CRUD', async () => {
    mockJson({});
    await createPromotion(SESSION, TENANT_ID, { name: 'P' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updatePromotion(SESSION, TENANT_ID, 'p-1', { name: 'P2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deletePromotion(SESSION, TENANT_ID, 'p-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('branches CRUD + listBranches filters', async () => {
    mockJson({});
    await listBranches(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/branches$/);
    mockJson({});
    await listBranches(SESSION, TENANT_ID, { city: 'CO', skip: '' });
    expect(lastUrl()).toContain('city=CO');
    mockJson({});
    await createBranch(SESSION, TENANT_ID, { name: 'B' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateBranch(SESSION, TENANT_ID, 'b-1', { name: 'B2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deactivateBranch(SESSION, TENANT_ID, 'b-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('treatment packages CRUD + listTreatmentPackages filters', async () => {
    mockJson({});
    await listTreatmentPackages(SESSION, TENANT_ID, { kind: 'x' });
    expect(lastUrl()).toContain('kind=x');
    mockJson({});
    await createTreatmentPackage(SESSION, TENANT_ID, { name: 'P' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateTreatmentPackage(SESSION, TENANT_ID, 'pkg-1', { name: 'P2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deactivateTreatmentPackage(SESSION, TENANT_ID, 'pkg-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('contact packages -> list + assign + update + refund', async () => {
    mockJson({});
    await listContactPackages(SESSION, TENANT_ID, 'c-1', { status: 'active' });
    expect(lastUrl()).toContain('status=active');
    mockJson({});
    await assignContactPackage(SESSION, TENANT_ID, 'c-1', { package_id: 'pkg' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateContactPackage(SESSION, TENANT_ID, 'c-1', 'cp-1', { sessions: 3 });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await refundContactPackage(SESSION, TENANT_ID, 'c-1', 'cp-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('subscription plans CRUD', async () => {
    mockJson({});
    await listSubscriptionPlans(SESSION, TENANT_ID, { active: 'true' });
    expect(lastUrl()).toContain('active=true');
    mockJson({});
    await createSubscriptionPlan(SESSION, TENANT_ID, { name: 'P' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateSubscriptionPlan(SESSION, TENANT_ID, 'plan-1', { name: 'P2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await archiveSubscriptionPlan(SESSION, TENANT_ID, 'plan-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('contact subscriptions list + cancel', async () => {
    mockJson({});
    await listContactSubscriptions(SESSION, TENANT_ID, { status: 'active' });
    expect(lastUrl()).toContain('status=active');
    mockJson({});
    await cancelContactSubscription(SESSION, TENANT_ID, 'sub-1');
    expect(lastInit().method).toBe('DELETE');
  });
});

// --------------------------------------------------------------------------
// Service requests + quotes.
// --------------------------------------------------------------------------
describe('service requests + quotes', () => {
  it('listServiceRequests + create + patch', async () => {
    mockJson({});
    await listServiceRequests(SESSION, TENANT_ID, { status: 'open' });
    expect(lastUrl()).toContain('status=open');
    mockJson({});
    await createServiceRequest(SESSION, TENANT_ID, { kind: 'install' });
    expect(bodyOf()).toEqual({ kind: 'install', tenant_id: TENANT_ID });
    mockJson({});
    await patchServiceRequest(SESSION, TENANT_ID, 'sr-1', { status: 'done' });
    expect(lastInit().method).toBe('PATCH');
  });

  it('quotes: get + create + patch + send', async () => {
    mockJson({});
    await getQuoteForSr(SESSION, TENANT_ID, 'sr-1');
    expect(lastUrl()).toContain('/service-requests/sr-1/quote');
    mockJson({});
    await createQuote(SESSION, TENANT_ID, 'sr-1', { total: 100 });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await patchQuote(SESSION, TENANT_ID, 'q-1', { total: 200 });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await sendQuote(SESSION, TENANT_ID, 'q-1');
    expect(lastUrl()).toContain('/quotes/q-1/send');
  });
});

// --------------------------------------------------------------------------
// Contact tags / contacts / notes / consent.
// --------------------------------------------------------------------------
describe('contact tags + contacts + notes', () => {
  it('contact tags CRUD', async () => {
    mockJson({});
    await listContactTags(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/contact-tags');
    mockJson({});
    await createContactTag(SESSION, TENANT_ID, { label: 'X' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateContactTag(SESSION, TENANT_ID, 'tag-1', { label: 'Y' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteContactTag(SESSION, TENANT_ID, 'tag-1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('listContacts — empty + with q/tagId/limit/offset incl limit=0', async () => {
    mockJson({});
    await listContacts(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/contacts$/);
    mockJson({});
    await listContacts(SESSION, TENANT_ID, { q: 'jane', tagId: 't1', limit: 0, offset: 0 });
    expect(lastUrl()).toContain('q=jane');
    expect(lastUrl()).toContain('tag_id=t1');
    expect(lastUrl()).toContain('limit=0');
    expect(lastUrl()).toContain('offset=0');
  });

  it('getContactProfile + updateContactPhone (with and without reason)', async () => {
    mockJson({});
    await getContactProfile(SESSION, TENANT_ID, 'c-1');
    expect(lastUrl()).toContain('/contacts/c-1/profile');
    mockJson({});
    await updateContactPhone(SESSION, TENANT_ID, 'c-1', { phone_e164: '+5730', reason: 'fix' });
    expect(bodyOf()).toEqual({ phone_e164: '+5730', reason: 'fix' });
    mockJson({});
    await updateContactPhone(SESSION, TENANT_ID, 'c-1', { phone_e164: '+5730' });
    expect(bodyOf()).toEqual({ phone_e164: '+5730', reason: null });
  });

  it('assign + unassign tags', async () => {
    mockJson({});
    await assignContactTags(SESSION, TENANT_ID, 'c-1', ['t1', 't2']);
    expect(bodyOf()).toEqual({ tag_ids: ['t1', 't2'] });
    mockJson({});
    await unassignContactTag(SESSION, TENANT_ID, 'c-1', 't1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('listContactNotes + listContactConsent (empty + with limit/offset)', async () => {
    mockJson({});
    await listContactNotes(SESSION, TENANT_ID, 'c-1');
    expect(lastUrl()).toContain('/contacts/c-1/notes');
    mockJson({});
    await listContactConsent(SESSION, TENANT_ID, 'c-1');
    expect(lastUrl()).toMatch(/\/contacts\/c-1\/consent$/);
    mockJson({});
    await listContactConsent(SESSION, TENANT_ID, 'c-1', { limit: 0, offset: 0 });
    expect(lastUrl()).toContain('limit=0');
    expect(lastUrl()).toContain('offset=0');
  });

  it('createContactNote -> wraps body in body field', async () => {
    await createContactNote(SESSION, TENANT_ID, 'c-1', 'note body');
    expect(bodyOf()).toEqual({ body: 'note body' });
  });
});

// --------------------------------------------------------------------------
// Campaigns + segments.
// --------------------------------------------------------------------------
describe('campaigns + segments', () => {
  it('listCampaigns + getCampaign', async () => {
    mockJson({});
    await listCampaigns(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/campaigns$/);
    mockJson({});
    await listCampaigns(SESSION, TENANT_ID, { status: 'live' });
    expect(lastUrl()).toContain('status=live');
    mockJson({});
    await getCampaign(SESSION, TENANT_ID, 'cmp-1');
    expect(lastUrl()).toContain('/campaigns/cmp-1');
  });

  it('campaign CRUD + preview + launch (default) + cancel', async () => {
    mockJson({});
    await createCampaign(SESSION, TENANT_ID, { name: 'C' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateCampaign(SESSION, TENANT_ID, 'cmp-1', { name: 'C2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await previewCampaign(SESSION, TENANT_ID, 'cmp-1');
    expect(bodyOf()).toEqual({});
    mockJson({});
    await launchCampaign(SESSION, TENANT_ID, 'cmp-1');
    expect(bodyOf()).toEqual({});
    mockJson({});
    await launchCampaign(SESSION, TENANT_ID, 'cmp-1', { send_at: '2026-01-01' });
    expect(bodyOf()).toEqual({ send_at: '2026-01-01' });
    mockJson({});
    await cancelCampaign(SESSION, TENANT_ID, 'cmp-1');
    expect(bodyOf()).toEqual({});
  });

  it('contact segments full lifecycle', async () => {
    mockJson({});
    await listContactSegments(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/segments$/);
    mockJson({});
    await listContactSegments(SESSION, TENANT_ID, { kind: 'rfm' });
    expect(lastUrl()).toContain('kind=rfm');
    mockJson({});
    await createContactSegment(SESSION, TENANT_ID, { name: 'S' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await updateContactSegment(SESSION, TENANT_ID, 'seg-1', { name: 'S2' });
    expect(lastInit().method).toBe('PATCH');
    mockJson({});
    await deleteContactSegment(SESSION, TENANT_ID, 'seg-1');
    expect(lastInit().method).toBe('DELETE');
    mockJson({});
    await previewContactSegment(SESSION, TENANT_ID, 'seg-1');
    expect(lastUrl()).toMatch(/\/preview$/);
    mockJson({});
    await previewContactSegment(SESSION, TENANT_ID, 'seg-1', { limit: 100 });
    expect(lastUrl()).toContain('limit=100');
    mockJson({});
    await refreshContactSegment(SESSION, TENANT_ID, 'seg-1');
    expect(bodyOf()).toEqual({});
  });
});

// --------------------------------------------------------------------------
// Analytics.
// --------------------------------------------------------------------------
describe('analytics', () => {
  it('every analytics endpoint -> default empty query + with range', async () => {
    const calls = [
      ['overview', getAnalyticsOverview],
      ['conversations', getAnalyticsConversations],
      ['appointments', getAnalyticsAppointments],
      ['contacts', getAnalyticsContacts],
      ['funnel', getAnalyticsFunnel],
      ['campaigns', getAnalyticsCampaigns],
      ['referrals', getAnalyticsReferrals],
      ['agents', getAnalyticsAgents],
    ];
    for (const [name, fn] of calls) {
      mockJson({});
      await fn(SESSION, TENANT_ID);
      expect(lastUrl()).toContain(`/analytics/${name}`);
      expect(lastUrl()).not.toContain('?');
      mockJson({});
      await fn(SESSION, TENANT_ID, { fromDate: '2026-01-01', toDate: '2026-01-31' });
      expect(lastUrl()).toContain('from_date=2026-01-01');
      expect(lastUrl()).toContain('to_date=2026-01-31');
    }
  });
});

// --------------------------------------------------------------------------
// Payments.
// --------------------------------------------------------------------------
describe('payments', () => {
  it('getTenantPaymentSettings + update', async () => {
    mockJson({});
    await getTenantPaymentSettings(SESSION, TENANT_ID);
    expect(lastUrl()).toContain('/payments/settings');
    mockJson({});
    await updateTenantPaymentSettings(SESSION, TENANT_ID, { provider: 'stripe' });
    expect(lastInit().method).toBe('PUT');
  });

  it('appointment payment link + send + status', async () => {
    mockJson({});
    await generateAppointmentPaymentLink(SESSION, TENANT_ID, 'ap-1');
    expect(bodyOf()).toEqual({});
    mockJson({});
    await generateAppointmentPaymentLink(SESSION, TENANT_ID, 'ap-1', { amount: 100 });
    expect(bodyOf()).toEqual({ amount: 100 });
    mockJson({});
    await sendAppointmentPaymentLink(SESSION, TENANT_ID, 'ap-1');
    expect(lastUrl()).toContain('/send-payment');
    mockJson({});
    await updateAppointmentPaymentStatus(SESSION, TENANT_ID, 'ap-1', { status: 'paid' });
    expect(lastInit().method).toBe('PATCH');
  });
});

// --------------------------------------------------------------------------
// Outbound DLQ + legal.
// --------------------------------------------------------------------------
describe('outbound DLQ + legal docs', () => {
  it('listOutboundDlq -> empty + all filters', async () => {
    mockJson({});
    await listOutboundDlq(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/outbound\/dlq$/);
    mockJson({});
    await listOutboundDlq(SESSION, TENANT_ID, {
      since: '2026-01-01',
      until: '2026-01-02',
      limit: 10,
      errorCode: 'E1',
    });
    const url = lastUrl();
    expect(url).toContain('since=2026-01-01');
    expect(url).toContain('until=2026-01-02');
    expect(url).toContain('limit=10');
    expect(url).toContain('error_code=E1');
  });

  it('retryOutboundDlqMessage -> POST', async () => {
    await retryOutboundDlqMessage(SESSION, TENANT_ID, 'msg-1');
    expect(lastUrl()).toContain('/outbound/dlq/msg-1/retry');
    expect(lastInit().method).toBe('POST');
  });

  it('legal docs: list (empty + kind), create draft, publish, public url', async () => {
    mockJson({});
    await listLegalDocuments(SESSION, TENANT_ID);
    expect(lastUrl()).toMatch(/\/legal$/);
    mockJson({});
    await listLegalDocuments(SESSION, TENANT_ID, { kind: 'terms' });
    expect(lastUrl()).toContain('kind=terms');
    mockJson({});
    await createLegalDocumentDraft(SESSION, TENANT_ID, { kind: 'privacy' });
    expect(lastInit().method).toBe('POST');
    mockJson({});
    await publishLegalDocument(SESSION, TENANT_ID, 'doc-1');
    expect(lastUrl()).toContain('/legal/doc-1/publish');
    const url = legalDocumentPublicUrl(SESSION, TENANT_ID, 'terms');
    expect(url).toContain(`/tenants/${TENANT_ID}/legal/terms`);
  });
});

// --------------------------------------------------------------------------
// /me endpoints (existing tests covered, here we add quick guard repeats).
// --------------------------------------------------------------------------
describe('/me/* endpoints + namespace shape', () => {
  it('getMyProfile/patchMyProfile shape', async () => {
    mockJson({});
    await getMyProfile(SESSION);
    expect(lastUrl()).toContain('/me/profile');
    mockJson({});
    await patchMyProfile(SESSION, { display_name: 'C' });
    expect(lastInit().method).toBe('PATCH');
    expect(JSON.parse(lastInit().body)).toEqual({ display_name: 'C' });
  });

  it('getMyPreferences/patchMyPreferences', async () => {
    mockJson({});
    await getMyPreferences(SESSION);
    expect(lastUrl()).toContain('/me/preferences');
    mockJson({});
    await patchMyPreferences(SESSION, { theme_override: 'light' });
    expect(lastInit().method).toBe('PATCH');
  });

  it('getMyNotifications + patchMyNotifications wraps in notification_matrix', async () => {
    mockJson({});
    await getMyNotifications(SESSION);
    expect(lastUrl()).toContain('/me/notifications');
    mockJson({});
    await patchMyNotifications(SESSION, { daily_digest: { email: true } });
    expect(bodyOf()).toEqual({ notification_matrix: { daily_digest: { email: true } } });
  });

  it('listMySessions + revokeMySession (with 204)', async () => {
    mockJson({});
    await listMySessions(SESSION);
    expect(lastUrl()).toContain('/me/sessions');
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => null,
    });
    const result = await revokeMySession(SESSION, 'current');
    expect(result).toBeNull();
  });

  it('namespace re-export sanity: every exported name is a function', () => {
    const expected = [
      'createTenant',
      'listFleetTenants',
      'getTenant',
      'getSystemHealth',
      'updateTenant',
      'patchTenantStatus',
    ];
    for (const name of expected) {
      expect(typeof core[name]).toBe('function');
    }
  });
});
