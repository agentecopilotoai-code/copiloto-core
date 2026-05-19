/**
 * Coverage push for useCampaignsData — exercises every mutation handler
 * (submit create/edit, preview, launch, cancel) plus toggle helpers and
 * error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listCampaigns: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  listContactTags: vi.fn(),
  listContactSegments: vi.fn(),
  createCampaign: vi.fn(),
  updateCampaign: vi.fn(),
  previewCampaign: vi.fn(),
  launchCampaign: vi.fn(),
  cancelCampaign: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useCampaignsData } from './useCampaignsData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const CAMPAIGN = {
  id: 'cam-1',
  name: 'Welcome wave',
  template_id: 'tpl-1',
  segment_filter: {},
};

function setupAll() {
  coreApi.listCampaigns.mockResolvedValue([CAMPAIGN]);
  coreApi.listWhatsappTemplates.mockResolvedValue([{ id: 'tpl-1', name: 'welcome' }]);
  coreApi.listContactTags.mockResolvedValue([{ id: 'tag-vip', label: 'VIP' }]);
  coreApi.listContactSegments.mockResolvedValue([{ id: 'seg-1', name: 'VIPs' }]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

async function renderCampaigns(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useCampaignsData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.campaigns.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useCampaignsData', () => {
  it('loads campaigns, templates, tags and segments on mount', async () => {
    const hook = await renderCampaigns();
    expect(coreApi.listCampaigns).toHaveBeenCalledWith(SESSION, 'tenant-acme');
    expect(coreApi.listWhatsappTemplates).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      { status: 'approved' },
    );
    expect(coreApi.listContactTags).toHaveBeenCalled();
    expect(coreApi.listContactSegments).toHaveBeenCalled();
    expect(hook.result.current.state.selectedId).toBe('cam-1');
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useCampaignsData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listCampaigns).not.toHaveBeenCalled();
  });

  it('surfaces an error notice when listCampaigns rejects', async () => {
    coreApi.listCampaigns.mockRejectedValueOnce(new Error('list-fail'));
    const { result } = renderHook(() => useCampaignsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    expect(result.current.state.notice.text).toBe('list-fail');
  });

  it('surfaces an error notice when listWhatsappTemplates rejects', async () => {
    coreApi.listWhatsappTemplates.mockRejectedValueOnce(new Error('tpl-fail'));
    const { result } = renderHook(() => useCampaignsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.text).toBe('tpl-fail'));
  });

  it('listContactTags / listContactSegments errors fall back to []', async () => {
    coreApi.listContactTags.mockRejectedValueOnce(new Error('tags-fail'));
    coreApi.listContactSegments.mockRejectedValueOnce(new Error('seg-fail'));
    const { result } = renderHook(() => useCampaignsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(coreApi.listCampaigns).toHaveBeenCalled());
    expect(result.current.state.availableTags).toEqual([]);
    expect(result.current.state.segments).toEqual([]);
  });

  it('clears selection when the list returns empty', async () => {
    coreApi.listCampaigns.mockResolvedValue([]);
    const { result } = renderHook(() => useCampaignsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(coreApi.listCampaigns).toHaveBeenCalled());
    await waitFor(() => expect(result.current.state.selectedId).toBeNull());
  });

  it('select / startCreate / startEdit / closeForm toggle form state', async () => {
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startCreate());
    expect(hook.result.current.state.showForm).toBe(true);
    expect(hook.result.current.state.formMode).toBe('create');

    act(() => hook.result.current.actions.startEdit(CAMPAIGN));
    expect(hook.result.current.state.formMode).toBe('edit');
    expect(hook.result.current.state.form.name).toBe('Welcome wave');

    act(() => hook.result.current.actions.closeForm());
    expect(hook.result.current.state.showForm).toBe(false);

    // startEdit with no campaign is a no-op.
    act(() => hook.result.current.actions.startEdit(null));
    expect(hook.result.current.state.showForm).toBe(false);

    act(() => hook.result.current.actions.select('cam-1'));
    expect(hook.result.current.state.selectedId).toBe('cam-1');
  });

  it('toggleTagInForm adds and removes a tag', async () => {
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startCreate());
    act(() => hook.result.current.actions.toggleTagInForm('tag-vip'));
    expect(hook.result.current.state.form.segment.tags).toContain('tag-vip');
    act(() => hook.result.current.actions.toggleTagInForm('tag-vip'));
    expect(hook.result.current.state.form.segment.tags).not.toContain('tag-vip');
  });

  it('submit-create posts a new campaign and refreshes', async () => {
    coreApi.createCampaign.mockResolvedValueOnce({ id: 'cam-new' });
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startCreate());
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'My new',
        template_id: 'tpl-1',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.createCampaign).toHaveBeenCalledTimes(1);
    expect(coreApi.listCampaigns).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('submit-edit posts updateCampaign with the editingId (BUG-038)', async () => {
    coreApi.updateCampaign.mockResolvedValueOnce({ id: 'cam-1' });
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startEdit(CAMPAIGN));
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'Renamed',
        template_id: 'tpl-1',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.updateCampaign).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'cam-1',
      expect.objectContaining({ name: 'Renamed' }),
    );
  });

  it('submit rejects when validation fails', async () => {
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startCreate());
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.createCampaign).not.toHaveBeenCalled();
  });

  it('submit surfaces an error notice when the API rejects', async () => {
    coreApi.createCampaign.mockRejectedValueOnce(new Error('create-fail'));
    const hook = await renderCampaigns();
    act(() => hook.result.current.actions.startCreate());
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'X',
        template_id: 'tpl-1',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.text).toBe('create-fail');
  });

  it('preview stores the preview rows', async () => {
    coreApi.previewCampaign.mockResolvedValueOnce({ recipients: 42 });
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.preview();
    });
    expect(hook.result.current.state.preview).toEqual({ recipients: 42 });
  });

  it('preview surfaces an error notice on rejection', async () => {
    coreApi.previewCampaign.mockRejectedValueOnce(new Error('preview-fail'));
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.preview();
    });
    expect(hook.result.current.state.notice?.text).toBe('preview-fail');
  });

  it('launch calls launchCampaign and refreshes', async () => {
    coreApi.launchCampaign.mockResolvedValueOnce({});
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.launch();
    });
    expect(coreApi.launchCampaign).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'cam-1', {});
    expect(coreApi.listCampaigns).toHaveBeenCalledTimes(2);
  });

  it('launch surfaces an error notice on rejection', async () => {
    coreApi.launchCampaign.mockRejectedValueOnce(new Error('launch-fail'));
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.launch();
    });
    expect(hook.result.current.state.notice?.text).toBe('launch-fail');
  });

  it('cancel calls cancelCampaign and refreshes', async () => {
    coreApi.cancelCampaign.mockResolvedValueOnce({});
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.cancel();
    });
    expect(coreApi.cancelCampaign).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'cam-1');
    expect(coreApi.listCampaigns).toHaveBeenCalledTimes(2);
  });

  it('cancel surfaces an error notice on rejection', async () => {
    coreApi.cancelCampaign.mockRejectedValueOnce(new Error('cancel-fail'));
    const hook = await renderCampaigns();
    await act(async () => {
      await hook.result.current.actions.cancel();
    });
    expect(hook.result.current.state.notice?.text).toBe('cancel-fail');
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.listCampaigns.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useCampaignsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    act(() => result.current.actions.dismissNotice());
    expect(result.current.state.notice).toBeNull();
  });
});
