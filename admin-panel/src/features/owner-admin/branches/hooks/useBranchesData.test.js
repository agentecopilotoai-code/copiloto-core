/**
 * Coverage push for useBranchesData — exercises every mutation handler
 * (save create/edit, deactivate) plus the opening-hours editing helpers
 * and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listBranches: vi.fn(),
  createBranch: vi.fn(),
  updateBranch: vi.fn(),
  deactivateBranch: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useBranchesData } from './useBranchesData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const BRANCH = {
  id: 'br-1',
  name: 'Sede Centro',
  code: 'CTR',
  address: 'Calle 1',
  city: 'Bogotá',
  state: 'Cundinamarca',
  country: 'CO',
  lat: 4.6,
  lng: -74.0,
  maps_url: '',
  phone_e164: '+571111',
  timezone: 'America/Bogota',
  opening_hours: { mon: [{ start: '09:00', end: '18:00' }] },
  is_active: true,
  sort_order: 0,
};

function setupAll() {
  coreApi.listBranches.mockResolvedValue([BRANCH]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

async function renderBranches(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useBranchesData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.branches.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useBranchesData', () => {
  it('loads branches on mount', async () => {
    const hook = await renderBranches();
    expect(coreApi.listBranches).toHaveBeenCalledWith(SESSION, 'tenant-acme', {});
    expect(hook.result.current.state.branches[0].id).toBe('br-1');
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useBranchesData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listBranches).not.toHaveBeenCalled();
  });

  it('surfaces an error when listBranches fails', async () => {
    coreApi.listBranches.mockRejectedValueOnce(new Error('list-fail'));
    const { result } = renderHook(() => useBranchesData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.error).toBe('list-fail'));
  });

  it('openCreate / openEdit / closeDrawer toggle drawer state', async () => {
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    expect(hook.result.current.state.drawerOpen).toBe(true);
    expect(hook.result.current.state.form.id).toBeNull();

    act(() => hook.result.current.actions.openEdit(BRANCH));
    expect(hook.result.current.state.form.id).toBe('br-1');

    act(() => hook.result.current.actions.closeDrawer());
    expect(hook.result.current.state.drawerOpen).toBe(false);
  });

  it('setFormField merges patches into the form', async () => {
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ name: 'Patched', code: 'P' }));
    expect(hook.result.current.state.form.name).toBe('Patched');
    expect(hook.result.current.state.form.code).toBe('P');
  });

  it('generateMapsUrl writes the computed url into the form', async () => {
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ lat: 4.6, lng: -74.0 }));
    act(() => hook.result.current.actions.generateMapsUrl());
    expect(hook.result.current.state.form.maps_url).toContain('google.com/maps');
  });

  it('opening-hours editors (addFranja/updateFranja/removeFranja)', async () => {
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());

    act(() => hook.result.current.actions.addFranja('mon'));
    expect(hook.result.current.state.form.opening_hours.mon.length).toBe(1);

    act(() => hook.result.current.actions.updateFranja('mon', 0, 'start', '10:00'));
    expect(hook.result.current.state.form.opening_hours.mon[0].start).toBe('10:00');

    act(() => hook.result.current.actions.removeFranja('mon', 0));
    expect(hook.result.current.state.form.opening_hours.mon.length).toBe(0);
  });

  it('save create posts createBranch and refreshes', async () => {
    coreApi.createBranch.mockResolvedValueOnce({ id: 'br-new' });
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    act(() =>
      hook.result.current.actions.setFormField({ name: 'Nueva', code: 'NUE' }),
    );
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(coreApi.createBranch).toHaveBeenCalled();
    expect(coreApi.listBranches).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.drawerOpen).toBe(false);
  });

  it('save edit posts updateBranch when form.id is set', async () => {
    coreApi.updateBranch.mockResolvedValueOnce({ id: 'br-1' });
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openEdit(BRANCH));
    act(() => hook.result.current.actions.setFormField({ name: 'Renamed' }));
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(coreApi.updateBranch).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'br-1',
      expect.objectContaining({ name: 'Renamed' }),
    );
  });

  it('save rejects when validation fails (missing name)', async () => {
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(hook.result.current.state.error).toBeTruthy();
    expect(coreApi.createBranch).not.toHaveBeenCalled();
  });

  it('save surfaces error message when API rejects', async () => {
    coreApi.createBranch.mockRejectedValueOnce(new Error('create-fail'));
    const hook = await renderBranches();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ name: 'X', code: 'X' }));
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(hook.result.current.state.error).toBe('create-fail');
  });

  it('deactivate calls deactivateBranch and refreshes', async () => {
    coreApi.deactivateBranch.mockResolvedValueOnce({});
    const hook = await renderBranches();
    await act(async () => {
      await hook.result.current.actions.deactivate(BRANCH);
    });
    expect(coreApi.deactivateBranch).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'br-1');
    expect(coreApi.listBranches).toHaveBeenCalledTimes(2);
  });

  it('deactivate surfaces error message when API rejects', async () => {
    coreApi.deactivateBranch.mockRejectedValueOnce(new Error('deact-fail'));
    const hook = await renderBranches();
    await act(async () => {
      await hook.result.current.actions.deactivate(BRANCH);
    });
    expect(hook.result.current.state.error).toBe('deact-fail');
  });

  it('dismissError clears the error', async () => {
    coreApi.listBranches.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useBranchesData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.error).toBe('boom'));
    act(() => result.current.actions.dismissError());
    expect(result.current.state.error).toBeNull();
  });

  it('refresh action re-runs the loader', async () => {
    const hook = await renderBranches();
    await act(async () => {
      await hook.result.current.actions.refresh();
    });
    expect(coreApi.listBranches).toHaveBeenCalledTimes(2);
  });
});
