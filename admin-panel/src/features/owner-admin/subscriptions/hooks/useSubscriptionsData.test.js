/**
 * Coverage push for useSubscriptionsData — exercises every mutation
 * handler (save create/edit, archivePlan, cancelSubscription) plus the
 * modal/form/tab helpers and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listSubscriptionPlans: vi.fn(),
  listContactSubscriptions: vi.fn(),
  createSubscriptionPlan: vi.fn(),
  updateSubscriptionPlan: vi.fn(),
  archiveSubscriptionPlan: vi.fn(),
  cancelContactSubscription: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useSubscriptionsData } from './useSubscriptionsData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const PLAN = {
  id: 'plan-1',
  name: 'Plan Oro',
  description: 'VIPs',
  billing_period: 'monthly',
  price_amount: 100,
  currency: 'COP',
  status: 'active',
};

const SUBSCRIBER = {
  id: 'sub-1',
  plan_id: 'plan-1',
  contact_display_name: 'Carla',
  contact_phone_e164: '+571111',
  status: 'active',
};

function setupAll() {
  coreApi.listSubscriptionPlans.mockResolvedValue([PLAN]);
  coreApi.listContactSubscriptions.mockResolvedValue([SUBSCRIBER]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

async function renderSubs(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useSubscriptionsData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.plans.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useSubscriptionsData', () => {
  it('loads plans + subscribers on mount and computes KPIs', async () => {
    const hook = await renderSubs();
    expect(coreApi.listSubscriptionPlans).toHaveBeenCalled();
    expect(coreApi.listContactSubscriptions).toHaveBeenCalled();
    expect(hook.result.current.state.kpis).toBeTruthy();
    expect(hook.result.current.state.visibleSubscribers.length).toBe(1);
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useSubscriptionsData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listSubscriptionPlans).not.toHaveBeenCalled();
  });

  it('surfaces an error message when the load fails', async () => {
    coreApi.listSubscriptionPlans.mockRejectedValueOnce(new Error('load-fail'));
    const { result } = renderHook(() => useSubscriptionsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.error).toBe('load-fail'));
  });

  it('openCreate / openEdit / closeModal toggle modal state', async () => {
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openCreate());
    expect(hook.result.current.state.modalOpen).toBe(true);
    expect(hook.result.current.state.form.id).toBeNull();

    act(() => hook.result.current.actions.openEdit(PLAN));
    expect(hook.result.current.state.form.id).toBe('plan-1');

    act(() => hook.result.current.actions.closeModal());
    expect(hook.result.current.state.modalOpen).toBe(false);
  });

  it('setFormField merges patches into the form', async () => {
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ name: 'Patched' }));
    expect(hook.result.current.state.form.name).toBe('Patched');
  });

  it('setSubscriberTab filters visible subscribers', async () => {
    const hook = await renderSubs();
    act(() => hook.result.current.actions.setSubscriberTab('cancelled'));
    expect(hook.result.current.state.subscriberTab).toBe('cancelled');
  });

  it('save create posts createSubscriptionPlan and refreshes', async () => {
    coreApi.createSubscriptionPlan.mockResolvedValueOnce({ id: 'plan-new' });
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ name: 'Nuevo' }));
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(coreApi.createSubscriptionPlan).toHaveBeenCalled();
    expect(coreApi.listSubscriptionPlans).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.modalOpen).toBe(false);
  });

  it('save edit posts updateSubscriptionPlan when form.id is set', async () => {
    coreApi.updateSubscriptionPlan.mockResolvedValueOnce({ id: 'plan-1' });
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openEdit(PLAN));
    act(() => hook.result.current.actions.setFormField({ name: 'Renamed' }));
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(coreApi.updateSubscriptionPlan).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'plan-1',
      expect.objectContaining({ name: 'Renamed' }),
    );
  });

  it('save rejects when name is empty', async () => {
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openCreate());
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(hook.result.current.state.error).toBeTruthy();
    expect(coreApi.createSubscriptionPlan).not.toHaveBeenCalled();
  });

  it('save surfaces error message when API rejects', async () => {
    coreApi.createSubscriptionPlan.mockRejectedValueOnce(new Error('create-fail'));
    const hook = await renderSubs();
    act(() => hook.result.current.actions.openCreate());
    act(() => hook.result.current.actions.setFormField({ name: 'X' }));
    await act(async () => {
      await hook.result.current.actions.save();
    });
    expect(hook.result.current.state.error).toBe('create-fail');
  });

  it('archivePlan calls archiveSubscriptionPlan and refreshes', async () => {
    coreApi.archiveSubscriptionPlan.mockResolvedValueOnce({});
    const hook = await renderSubs();
    await act(async () => {
      await hook.result.current.actions.archivePlan(PLAN);
    });
    expect(coreApi.archiveSubscriptionPlan).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'plan-1');
    expect(coreApi.listSubscriptionPlans).toHaveBeenCalledTimes(2);
  });

  it('archivePlan surfaces error message when API rejects', async () => {
    coreApi.archiveSubscriptionPlan.mockRejectedValueOnce(new Error('archive-fail'));
    const hook = await renderSubs();
    await act(async () => {
      await hook.result.current.actions.archivePlan(PLAN);
    });
    expect(hook.result.current.state.error).toBe('archive-fail');
  });

  it('cancelSubscription calls cancelContactSubscription and refreshes', async () => {
    coreApi.cancelContactSubscription.mockResolvedValueOnce({});
    const hook = await renderSubs();
    await act(async () => {
      await hook.result.current.actions.cancelSubscription(SUBSCRIBER);
    });
    expect(coreApi.cancelContactSubscription).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'sub-1');
    expect(coreApi.listSubscriptionPlans).toHaveBeenCalledTimes(2);
  });

  it('cancelSubscription surfaces error message when API rejects', async () => {
    coreApi.cancelContactSubscription.mockRejectedValueOnce(new Error('cancel-fail'));
    const hook = await renderSubs();
    await act(async () => {
      await hook.result.current.actions.cancelSubscription(SUBSCRIBER);
    });
    expect(hook.result.current.state.error).toBe('cancel-fail');
  });

  it('dismissError clears the error', async () => {
    coreApi.listSubscriptionPlans.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useSubscriptionsData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.error).toBe('boom'));
    act(() => result.current.actions.dismissError());
    expect(result.current.state.error).toBeNull();
  });

  it('refresh action re-runs the loader', async () => {
    const hook = await renderSubs();
    await act(async () => {
      await hook.result.current.actions.refresh();
    });
    expect(coreApi.listSubscriptionPlans).toHaveBeenCalledTimes(2);
  });
});
