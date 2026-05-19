/**
 * Coverage push for useTenantSetupData — exercises the load-on-mount flow,
 * tenant save, settings save, status patch, brand logo upload/clear,
 * reindex, audit refresh, and the side-panels handlers (tags, payment,
 * retention).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  getTenant: vi.fn(),
  getTenantSettings: vi.fn(),
  createTenant: vi.fn(),
  updateTenant: vi.fn(),
  updateTenantSettings: vi.fn(),
  patchTenantStatus: vi.fn(),
  reindexAllKnowledgeDocuments: vi.fn(),
  uploadTenantBrandLogo: vi.fn(),
  listAuditLogs: vi.fn(),
  listContactTags: vi.fn(),
  createContactTag: vi.fn(),
  updateContactTag: vi.fn(),
  deleteContactTag: vi.fn(),
  getTenantPaymentSettings: vi.fn(),
  updateTenantPaymentSettings: vi.fn(),
  listRetentionPolicies: vi.fn(),
  getRetentionPreview: vi.fn(),
  updateRetentionPolicies: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useTenantSetupData } from './useTenantSetupData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const TENANT_DETAILS = {
  id: 'tenant-acme',
  slug: 'acme',
  legal_name: 'Acme S.A.S.',
  display_name: 'Acme',
  business_type_label: 'Salud',
  vertical_code: 'health',
  country_code: 'CO',
  timezone: 'America/Bogota',
  status: 'active',
};

const TENANT_SETTINGS = {
  locale: 'es-CO',
  business_hours: {},
  escalation_policy: {},
  pii_policy: {},
  no_train: true,
  notification_settings: {},
  bot_personality: {},
  brand_logo_url: 'https://logo.png',
};

function setupAll() {
  coreApi.getTenant.mockResolvedValue(TENANT_DETAILS);
  coreApi.getTenantSettings.mockResolvedValue(TENANT_SETTINGS);
  coreApi.listContactTags.mockResolvedValue([{ id: 'tag-1', name: 'VIP' }]);
  coreApi.getTenantPaymentSettings.mockResolvedValue({
    provider: 'stripe',
    currency: 'COP',
    default_amount: 100,
    api_key_configured: true,
    webhook_secret_configured: false,
  });
  coreApi.listRetentionPolicies.mockResolvedValue({ policies: [] });
  coreApi.getRetentionPreview.mockResolvedValue({ preview: [] });
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

const noop = () => {};
const event = () => ({ preventDefault: noop });

async function renderSetup(opts = {}) {
  const {
    session = SESSION,
    tenant = TENANT,
    onTenantCreated = vi.fn(),
    setActiveTab = vi.fn(),
  } = opts;
  const hook = renderHook(() =>
    useTenantSetupData({ session, tenant, onTenantCreated, setActiveTab }),
  );
  await waitFor(() => expect(coreApi.getTenant).toHaveBeenCalled());
  // Also wait for the tenant form to be hydrated.
  await waitFor(() =>
    expect(hook.result.current.state.tenantForm.slug).toBe('acme'),
  );
  return { hook, onTenantCreated, setActiveTab };
}

describe('useTenantSetupData', () => {
  it('loads tenant + settings + side-panel data on mount', async () => {
    const { hook } = await renderSetup();
    expect(coreApi.getTenantSettings).toHaveBeenCalled();
    expect(coreApi.listContactTags).toHaveBeenCalled();
    expect(coreApi.getTenantPaymentSettings).toHaveBeenCalled();
    expect(coreApi.listRetentionPolicies).toHaveBeenCalled();
    expect(hook.result.current.state.tenantForm.legal_name).toBe('Acme S.A.S.');
    expect(hook.result.current.state.brandLogoUrl).toBe('https://logo.png');
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() =>
      useTenantSetupData({
        session: SESSION,
        tenant: undefined,
        onTenantCreated: noop,
        setActiveTab: noop,
      }),
    );
    expect(coreApi.getTenant).not.toHaveBeenCalled();
  });

  it('does not crash when getTenant rejects', async () => {
    coreApi.getTenant.mockRejectedValueOnce(new Error('tenant-fail'));
    const { result } = renderHook(() =>
      useTenantSetupData({ session: SESSION, tenant: TENANT, onTenantCreated: noop, setActiveTab: noop }),
    );
    await waitFor(() => expect(coreApi.getTenant).toHaveBeenCalled());
    // Editable defaults kept; should not throw.
    expect(result.current.state.tenantForm.slug).toBe('tenant-demo');
  });

  it('handleSaveTenant calls updateTenant when tenant is known', async () => {
    coreApi.updateTenant.mockResolvedValueOnce({ id: 'tenant-acme', slug: 'acme' });
    const { hook, onTenantCreated, setActiveTab } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleSaveTenant(event());
    });
    expect(coreApi.updateTenant).toHaveBeenCalled();
    expect(onTenantCreated).toHaveBeenCalled();
    expect(setActiveTab).toHaveBeenCalledWith('settings');
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('handleSaveTenant calls createTenant when no tenant id', async () => {
    coreApi.createTenant.mockResolvedValueOnce({ id: 'new-tenant', slug: 'new' });
    const hook = renderHook(() =>
      useTenantSetupData({
        session: SESSION,
        tenant: undefined,
        onTenantCreated: vi.fn(),
        setActiveTab: vi.fn(),
      }),
    );
    await act(async () => {
      await hook.result.current.actions.handleSaveTenant(event());
    });
    expect(coreApi.createTenant).toHaveBeenCalled();
  });

  it('handleSaveTenant surfaces error notice on failure', async () => {
    coreApi.updateTenant.mockRejectedValueOnce(new Error('save-fail'));
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleSaveTenant(event());
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
  });

  it('handleSaveSettings calls updateTenantSettings + refreshes audit', async () => {
    coreApi.updateTenantSettings.mockResolvedValueOnce({ ...TENANT_SETTINGS });
    coreApi.listAuditLogs.mockResolvedValueOnce([{ id: 'a-1', action: 'settings.update' }]);
    const { hook, setActiveTab } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleSaveSettings(event());
    });
    expect(coreApi.updateTenantSettings).toHaveBeenCalled();
    expect(setActiveTab).toHaveBeenCalledWith('audit');
  });

  it('handleSaveSettings rejects when no tenant id', async () => {
    const hook = renderHook(() =>
      useTenantSetupData({
        session: SESSION,
        tenant: undefined,
        onTenantCreated: noop,
        setActiveTab: noop,
      }),
    );
    await act(async () => {
      await hook.result.current.actions.handleSaveSettings(event());
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.updateTenantSettings).not.toHaveBeenCalled();
  });

  it('handleChangeStatus calls patchTenantStatus and refreshes audit', async () => {
    coreApi.patchTenantStatus.mockResolvedValueOnce({ status: 'suspended' });
    coreApi.listAuditLogs.mockResolvedValueOnce([]);
    const { hook } = await renderSetup();
    act(() => hook.result.current.actions.setTargetStatus('suspended'));
    await act(async () => {
      await hook.result.current.actions.handleChangeStatus(event());
    });
    expect(coreApi.patchTenantStatus).toHaveBeenCalled();
    expect(hook.result.current.state.tenantStatus).toBe('suspended');
  });

  it('handleProviderChange updates the rag form', async () => {
    const { hook } = await renderSetup();
    act(() => hook.result.current.actions.handleProviderChange('openai'));
    expect(hook.result.current.state.ragForm.provider).toBe('openai');
  });

  it('handleReindexAll calls reindexAllKnowledgeDocuments and stores result', async () => {
    coreApi.reindexAllKnowledgeDocuments.mockResolvedValueOnce({
      indexed: 5,
      failed: 0,
      embedding_provider: 'openai',
    });
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleReindexAll(event());
    });
    expect(coreApi.reindexAllKnowledgeDocuments).toHaveBeenCalled();
    expect(hook.result.current.state.reindexResult).toEqual({
      indexed: 5,
      failed: 0,
      embedding_provider: 'openai',
    });
  });

  it('handleUploadBrandLogo uploads and reflects the new URL', async () => {
    coreApi.uploadTenantBrandLogo.mockResolvedValueOnce({
      ...TENANT_SETTINGS,
      brand_logo_url: 'https://logo2.png',
    });
    const { hook } = await renderSetup();
    const file = new Blob(['file']);
    await act(async () => {
      await hook.result.current.actions.handleUploadBrandLogo(file);
    });
    expect(coreApi.uploadTenantBrandLogo).toHaveBeenCalled();
    expect(hook.result.current.state.brandLogoUrl).toBe('https://logo2.png');
  });

  it('handleUploadBrandLogo is a no-op without file', async () => {
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleUploadBrandLogo(null);
    });
    expect(coreApi.uploadTenantBrandLogo).not.toHaveBeenCalled();
  });

  it('handleClearBrandLogo clears the logo via PATCH', async () => {
    coreApi.updateTenantSettings.mockResolvedValueOnce({
      ...TENANT_SETTINGS,
      brand_logo_url: null,
    });
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleClearBrandLogo();
    });
    expect(coreApi.updateTenantSettings).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      { brand_logo_url: '' },
    );
    expect(hook.result.current.state.brandLogoUrl).toBeNull();
  });

  it('refreshAuditLogs fetches and stores audit logs', async () => {
    coreApi.listAuditLogs.mockResolvedValueOnce([{ id: 'a-1' }]);
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.refreshAuditLogs();
    });
    expect(coreApi.listAuditLogs).toHaveBeenCalled();
    expect(hook.result.current.state.auditLogs.length).toBe(1);
  });

  // ── Side-panel actions ───────────────────────────────────────────────────

  it('handleSaveTag creates a new tag when not editing', async () => {
    coreApi.createContactTag.mockResolvedValueOnce({ id: 'tag-new' });
    const { hook } = await renderSetup();
    act(() =>
      hook.result.current.actions.setTagForm({
        name: 'New Tag',
        color: '#000000',
        description: '',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.handleSaveTag(event());
    });
    expect(coreApi.createContactTag).toHaveBeenCalled();
  });

  it('handleSaveTag updates an existing tag when editing', async () => {
    coreApi.updateContactTag.mockResolvedValueOnce({ id: 'tag-1' });
    const { hook } = await renderSetup();
    act(() =>
      hook.result.current.actions.startEditingTag({ id: 'tag-1', name: 'VIP', color: '#fff', description: '' }),
    );
    await act(async () => {
      await hook.result.current.actions.handleSaveTag(event());
    });
    expect(coreApi.updateContactTag).toHaveBeenCalled();
  });

  it('handleSaveTag is a no-op with empty name', async () => {
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleSaveTag(event());
    });
    expect(coreApi.createContactTag).not.toHaveBeenCalled();
  });

  it('cancelEditingTag clears the editing state', async () => {
    const { hook } = await renderSetup();
    act(() => hook.result.current.actions.startEditingTag({ id: 'tag-1', name: 'VIP' }));
    act(() => hook.result.current.actions.cancelEditingTag());
    expect(hook.result.current.state.editingTagId).toBeNull();
    expect(hook.result.current.state.tagForm.name).toBe('');
  });

  it('handleDeleteTag calls deleteContactTag and refreshes', async () => {
    coreApi.deleteContactTag.mockResolvedValueOnce({});
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleDeleteTag('tag-1');
    });
    expect(coreApi.deleteContactTag).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'tag-1');
  });

  it('handleSavePaymentSettings posts updateTenantPaymentSettings', async () => {
    coreApi.updateTenantPaymentSettings.mockResolvedValueOnce({
      provider: 'stripe',
      currency: 'COP',
      default_amount: 200,
      api_key_configured: true,
      webhook_secret_configured: true,
    });
    const { hook } = await renderSetup();
    await act(async () => {
      await hook.result.current.actions.handleSavePaymentSettings(event());
    });
    expect(coreApi.updateTenantPaymentSettings).toHaveBeenCalled();
  });

  it('updateRetentionRow patches a retention policy row', async () => {
    const { hook } = await renderSetup();
    await waitFor(() => expect(hook.result.current.state.retentionPolicies.length).toBeGreaterThan(0));
    const firstEntity = hook.result.current.state.retentionPolicies[0].entity;
    act(() =>
      hook.result.current.actions.updateRetentionRow(firstEntity, { retention_days: 99 }),
    );
    expect(
      hook.result.current.state.retentionPolicies.find((r) => r.entity === firstEntity)
        .retention_days,
    ).toBe(99);
  });

  it('handleSaveRetention posts updateRetentionPolicies', async () => {
    coreApi.updateRetentionPolicies.mockResolvedValueOnce({});
    const { hook } = await renderSetup();
    await waitFor(() => expect(hook.result.current.state.retentionPolicies.length).toBeGreaterThan(0));
    await act(async () => {
      await hook.result.current.actions.handleSaveRetention(event());
    });
    expect(coreApi.updateRetentionPolicies).toHaveBeenCalled();
  });

  it('refreshContactTags reloads the tag list', async () => {
    const { hook } = await renderSetup();
    coreApi.listContactTags.mockResolvedValueOnce([{ id: 't-2', name: 'Other' }]);
    await act(async () => {
      await hook.result.current.actions.refreshContactTags(undefined, true);
    });
    expect(hook.result.current.state.contactTags[0].id).toBe('t-2');
  });

  it('refreshRetention reloads policies + preview', async () => {
    const { hook } = await renderSetup();
    coreApi.listRetentionPolicies.mockResolvedValueOnce({ policies: [] });
    coreApi.getRetentionPreview.mockResolvedValueOnce({ preview: [{ entity: 'messages' }] });
    await act(async () => {
      await hook.result.current.actions.refreshRetention();
    });
    expect(hook.result.current.state.retentionPreview.length).toBe(1);
  });
});
