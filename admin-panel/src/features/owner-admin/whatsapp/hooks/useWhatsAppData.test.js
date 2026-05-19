/**
 * Coverage push for useWhatsAppData — exercises the health load, the
 * channel upsert, template create/sync/delete and error / 404 branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  getWhatsAppChannelHealth: vi.fn(),
  upsertWhatsAppChannel: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  createWhatsappTemplate: vi.fn(),
  syncWhatsappTemplates: vi.fn(),
  deleteWhatsappTemplate: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useWhatsAppData } from './useWhatsAppData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const HEALTH = {
  channel: {
    business_id: 'biz-1',
    waba_id: 'waba-1',
    phone_number_id: 'phn-1',
    account_mode: 'mock',
  },
  ready: true,
};

const TEMPLATE = {
  id: 'tpl-1',
  name: 'welcome',
  locale: 'es',
  category: 'utility',
  purpose: 'appointment_confirmation',
};

function setupAll() {
  coreApi.getWhatsAppChannelHealth.mockResolvedValue(HEALTH);
  coreApi.listWhatsappTemplates.mockResolvedValue([TEMPLATE]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

async function renderWa(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useWhatsAppData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.health).toBeTruthy();
  });
  return hook;
}

describe('useWhatsAppData', () => {
  it('loads health + templates on mount and seeds the form from channel', async () => {
    const hook = await renderWa();
    expect(coreApi.getWhatsAppChannelHealth).toHaveBeenCalled();
    expect(coreApi.listWhatsappTemplates).toHaveBeenCalled();
    expect(hook.result.current.state.form.business_id).toBe('biz-1');
    expect(hook.result.current.state.templates.length).toBe(1);
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useWhatsAppData({ session: SESSION, tenant: undefined }));
    expect(coreApi.getWhatsAppChannelHealth).not.toHaveBeenCalled();
  });

  it('treats 404 from getWhatsAppChannelHealth as "no channel yet"', async () => {
    const err = Object.assign(new Error('not found'), { status: 404 });
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(err);
    const { result } = renderHook(() => useWhatsAppData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(coreApi.getWhatsAppChannelHealth).toHaveBeenCalled());
    expect(result.current.state.loadError).toBeNull();
  });

  it('non-404 health error sets loadError and notice', async () => {
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const { result } = renderHook(() => useWhatsAppData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    expect(result.current.state.loadError).toBeTruthy();
  });

  it('updateField updates the form', async () => {
    const hook = await renderWa();
    act(() => hook.result.current.actions.updateField('business_id', 'new-biz'));
    expect(hook.result.current.state.form.business_id).toBe('new-biz');
  });

  it('submitChannel posts upsertWhatsAppChannel and reloads health', async () => {
    coreApi.upsertWhatsAppChannel.mockResolvedValueOnce({ id: 'ch-1' });
    coreApi.getWhatsAppChannelHealth.mockResolvedValueOnce(HEALTH); // for refreshHealth
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.submitChannel();
    });
    expect(coreApi.upsertWhatsAppChannel).toHaveBeenCalled();
  });

  it('submitChannel rejects when there is no tenant', () => {
    const { result } = renderHook(() => useWhatsAppData({ session: SESSION, tenant: undefined }));
    return act(async () => {
      await result.current.actions.submitChannel();
    }).then(() => {
      expect(result.current.state.notice?.type).toBe('error');
      expect(coreApi.upsertWhatsAppChannel).not.toHaveBeenCalled();
    });
  });

  it('submitChannel rejects while loadError is set', async () => {
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const { result } = renderHook(() => useWhatsAppData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.loadError).toBeTruthy());
    await act(async () => {
      await result.current.actions.submitChannel();
    });
    expect(coreApi.upsertWhatsAppChannel).not.toHaveBeenCalled();
  });

  it('submitChannel surfaces an error notice when upsert rejects', async () => {
    coreApi.upsertWhatsAppChannel.mockRejectedValueOnce(new Error('upsert-fail'));
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.submitChannel();
    });
    expect(hook.result.current.state.notice?.text).toBe('upsert-fail');
  });

  it('refreshHealth re-fetches and surfaces success', async () => {
    const hook = await renderWa();
    coreApi.getWhatsAppChannelHealth.mockResolvedValueOnce(HEALTH);
    await act(async () => {
      await hook.result.current.actions.refreshHealth();
    });
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('refreshHealth handles 404 with friendly notice', async () => {
    const hook = await renderWa();
    const err = Object.assign(new Error('nope'), { status: 404 });
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(err);
    await act(async () => {
      await hook.result.current.actions.refreshHealth();
    });
    expect(hook.result.current.state.notice?.type).toBe('success');
    expect(hook.result.current.state.health).toBeNull();
  });

  it('refreshHealth surfaces an error notice for non-404 failures', async () => {
    const hook = await renderWa();
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(
      Object.assign(new Error('refresh-fail'), { status: 500 }),
    );
    await act(async () => {
      await hook.result.current.actions.refreshHealth();
    });
    expect(hook.result.current.state.notice?.text).toBe('refresh-fail');
  });

  it('createTemplate posts a new template and reloads', async () => {
    coreApi.createWhatsappTemplate.mockResolvedValueOnce({});
    const hook = await renderWa();
    act(() =>
      hook.result.current.actions.setTemplateForm({
        name: 'new_template',
        locale: 'es',
        category: 'utility',
        purpose: 'appointment_confirmation',
        header: '',
        body: 'Hello {{1}}',
        footer: '',
        buttons: '',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.createTemplate();
    });
    expect(coreApi.createWhatsappTemplate).toHaveBeenCalled();
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('createTemplate rejects when form is invalid', async () => {
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.createTemplate();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.createWhatsappTemplate).not.toHaveBeenCalled();
  });

  it('createTemplate surfaces an error notice on API failure', async () => {
    coreApi.createWhatsappTemplate.mockRejectedValueOnce(new Error('tpl-fail'));
    const hook = await renderWa();
    act(() =>
      hook.result.current.actions.setTemplateForm({
        name: 'name_ok',
        locale: 'es',
        category: 'utility',
        purpose: 'appointment_confirmation',
        header: '',
        body: 'hello',
        footer: '',
        buttons: '',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.createTemplate();
    });
    expect(hook.result.current.state.notice?.text).toBe('tpl-fail');
  });

  it('syncTemplates calls syncWhatsappTemplates and reloads', async () => {
    coreApi.syncWhatsappTemplates.mockResolvedValueOnce({ updated: 2, meta_total: 5 });
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.syncTemplates();
    });
    expect(coreApi.syncWhatsappTemplates).toHaveBeenCalled();
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('syncTemplates surfaces an error notice on rejection', async () => {
    coreApi.syncWhatsappTemplates.mockRejectedValueOnce(new Error('sync-fail'));
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.syncTemplates();
    });
    expect(hook.result.current.state.notice?.text).toBe('sync-fail');
  });

  it('deleteTemplate posts deleteWhatsappTemplate and reloads', async () => {
    coreApi.deleteWhatsappTemplate.mockResolvedValueOnce({});
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.deleteTemplate(TEMPLATE);
    });
    expect(coreApi.deleteWhatsappTemplate).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'tpl-1');
  });

  it('deleteTemplate surfaces an error notice on rejection', async () => {
    coreApi.deleteWhatsappTemplate.mockRejectedValueOnce(new Error('del-fail'));
    const hook = await renderWa();
    await act(async () => {
      await hook.result.current.actions.deleteTemplate(TEMPLATE);
    });
    expect(hook.result.current.state.notice?.text).toBe('del-fail');
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.getWhatsAppChannelHealth.mockRejectedValueOnce(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const { result } = renderHook(() => useWhatsAppData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    act(() => result.current.actions.dismissNotice());
    expect(result.current.state.notice).toBeNull();
  });
});
