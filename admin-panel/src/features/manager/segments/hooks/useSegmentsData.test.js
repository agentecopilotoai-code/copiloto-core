/**
 * Coverage push for useSegmentsData — exercises every mutation handler
 * (submit-create, submit-edit, preview, refresh, remove) plus the rule
 * builder helpers and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listContactSegments: vi.fn(),
  createContactSegment: vi.fn(),
  updateContactSegment: vi.fn(),
  deleteContactSegment: vi.fn(),
  previewContactSegment: vi.fn(),
  refreshContactSegment: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useSegmentsData } from './useSegmentsData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const SEG_DYNAMIC = {
  id: 'seg-1',
  name: 'VIPs',
  description: 'High-value contacts',
  kind: 'dynamic',
  rules: { all_of: [{ field: 'total_spent', op: 'gte', value: 1000 }] },
  is_system: false,
};

const SEG_SYSTEM = {
  id: 'seg-sys',
  name: 'System segment',
  kind: 'dynamic',
  rules: {},
  is_system: true,
};

function setupList(segments = [SEG_DYNAMIC]) {
  coreApi.listContactSegments.mockResolvedValue(segments);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupList();
});

async function renderSegments(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useSegmentsData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.segments.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useSegmentsData', () => {
  it('loads segments on mount and auto-selects the first one', async () => {
    const hook = await renderSegments();
    expect(coreApi.listContactSegments).toHaveBeenCalledWith(SESSION, 'tenant-acme');
    expect(hook.result.current.state.selectedId).toBe('seg-1');
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useSegmentsData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listContactSegments).not.toHaveBeenCalled();
  });

  it('surfaces an error notice when listContactSegments rejects', async () => {
    coreApi.listContactSegments.mockRejectedValueOnce(new Error('list-boom'));
    const { result } = renderHook(() => useSegmentsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    expect(result.current.state.notice.text).toBe('list-boom');
  });

  it('clears selection when the list returns empty', async () => {
    setupList([]);
    const { result } = renderHook(() => useSegmentsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(coreApi.listContactSegments).toHaveBeenCalled());
    await waitFor(() => expect(result.current.state.selectedId).toBeNull());
  });

  it('select / startCreate / startEdit / closeForm toggle form state', async () => {
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startCreate());
    expect(hook.result.current.state.showForm).toBe(true);
    expect(hook.result.current.state.formMode).toBe('create');

    act(() => hook.result.current.actions.startEdit(SEG_DYNAMIC));
    expect(hook.result.current.state.formMode).toBe('edit');
    expect(hook.result.current.state.form.name).toBe('VIPs');

    act(() => hook.result.current.actions.closeForm());
    expect(hook.result.current.state.showForm).toBe(false);

    // startEdit with no segment is a no-op.
    act(() => hook.result.current.actions.startEdit(null));
    expect(hook.result.current.state.showForm).toBe(false);

    act(() => hook.result.current.actions.select('seg-1'));
    expect(hook.result.current.state.selectedId).toBe('seg-1');
  });

  it('exercises rule-builder handlers (add/remove/changeField/changeOp/changeValue/blurList)', async () => {
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startCreate());
    act(() => hook.result.current.actions.addRule());
    expect(hook.result.current.state.form.items.length).toBe(2);

    act(() => hook.result.current.actions.changeRuleField(1, 'tags'));
    expect(hook.result.current.state.form.items[1].field).toBe('tags');

    act(() => hook.result.current.actions.changeRuleOp(1, 'contains_all'));
    expect(hook.result.current.state.form.items[1].op).toBe('contains_all');

    act(() => hook.result.current.actions.changeRuleValue(1, 'vip,gold'));
    expect(hook.result.current.state.form.items[1].value).toBe('vip,gold');

    act(() => hook.result.current.actions.blurRuleListValue(1, 'vip, gold, silver'));
    expect(hook.result.current.state.form.items[1].value).toEqual(['vip', 'gold', 'silver']);

    act(() => hook.result.current.actions.removeRule(1));
    expect(hook.result.current.state.form.items.length).toBe(1);
  });

  it('submit-create posts a new segment and refreshes the list', async () => {
    coreApi.createContactSegment.mockResolvedValueOnce({ id: 'seg-new' });
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startCreate());
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'Nuevo',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.createContactSegment).toHaveBeenCalledTimes(1);
    expect(coreApi.listContactSegments).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.notice?.type).toBe('success');
    expect(hook.result.current.state.showForm).toBe(false);
  });

  it('submit-edit posts updateContactSegment with the editingId (BUG-039)', async () => {
    coreApi.updateContactSegment.mockResolvedValueOnce({ id: 'seg-1' });
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startEdit(SEG_DYNAMIC));
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'Renamed',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.updateContactSegment).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'seg-1',
      expect.objectContaining({ name: 'Renamed' }),
    );
  });

  it('submit rejects when name is empty', async () => {
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startCreate());
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.createContactSegment).not.toHaveBeenCalled();
  });

  it('submit surfaces an error notice when the API rejects', async () => {
    coreApi.createContactSegment.mockRejectedValueOnce(new Error('create-fail'));
    const hook = await renderSegments();
    act(() => hook.result.current.actions.startCreate());
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'X',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('create-fail');
  });

  it('preview happy path stores the preview rows', async () => {
    coreApi.previewContactSegment.mockResolvedValueOnce({ rows: [{ id: 'c-1' }] });
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.preview();
    });
    expect(hook.result.current.state.preview).toEqual({ rows: [{ id: 'c-1' }] });
  });

  it('preview surfaces an error notice when the API rejects', async () => {
    coreApi.previewContactSegment.mockRejectedValueOnce(new Error('preview-fail'));
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.preview();
    });
    expect(hook.result.current.state.notice?.text).toBe('preview-fail');
  });

  it('refresh recalcula segment + refresca lista', async () => {
    coreApi.refreshContactSegment.mockResolvedValueOnce({});
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.refresh();
    });
    expect(coreApi.refreshContactSegment).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'seg-1');
    expect(coreApi.listContactSegments).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('refresh surfaces an error notice on failure', async () => {
    coreApi.refreshContactSegment.mockRejectedValueOnce(new Error('refresh-fail'));
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.refresh();
    });
    expect(hook.result.current.state.notice?.text).toBe('refresh-fail');
  });

  it('remove deletes the segment and refreshes', async () => {
    coreApi.deleteContactSegment.mockResolvedValueOnce({});
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.remove();
    });
    expect(coreApi.deleteContactSegment).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'seg-1');
    expect(coreApi.listContactSegments).toHaveBeenCalledTimes(2);
  });

  it('remove blocks system segments', async () => {
    setupList([SEG_SYSTEM]);
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.remove();
    });
    expect(coreApi.deleteContactSegment).not.toHaveBeenCalled();
    expect(hook.result.current.state.notice?.type).toBe('error');
  });

  it('remove surfaces an error notice on failure', async () => {
    coreApi.deleteContactSegment.mockRejectedValueOnce(new Error('delete-fail'));
    const hook = await renderSegments();
    await act(async () => {
      await hook.result.current.actions.remove();
    });
    expect(hook.result.current.state.notice?.text).toBe('delete-fail');
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.listContactSegments.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useSegmentsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    act(() => result.current.actions.dismissNotice());
    expect(result.current.state.notice).toBeNull();
  });
});
