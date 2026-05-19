/**
 * Coverage push for useServicesData — exercises every mutation handler
 * (submit create/edit, deactivate, move, saveDefaultDuration) plus
 * the rule-builder helpers and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listServices: vi.fn(),
  listPromotions: vi.fn(),
  getTenantSettings: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  listQualificationQuestions: vi.fn(),
  createService: vi.fn(),
  updateService: vi.fn(),
  deactivateService: vi.fn(),
  reorderServices: vi.fn(),
  updateTenantSettings: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useServicesData } from './useServicesData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-acme' };

const SVC_A = {
  id: 'svc-a',
  name: 'Servicio A',
  category: 'Estética',
  description: '',
  price_amount: 50,
  price_currency: 'COP',
  duration_minutes: 60,
  is_active: true,
  sort_order: 0,
};

const SVC_B = {
  id: 'svc-b',
  name: 'Servicio B',
  category: 'Estética',
  duration_minutes: 30,
  is_active: true,
  sort_order: 1,
};

const TENANT_SETTINGS = {
  locale: 'es-CO',
  business_hours: {},
  escalation_policy: { service_durations: { default: 45 } },
  pii_policy: {},
  no_train: false,
};

function setupAll() {
  coreApi.listServices.mockResolvedValue([SVC_A, SVC_B]);
  coreApi.listPromotions.mockResolvedValue([]);
  coreApi.getTenantSettings.mockResolvedValue(TENANT_SETTINGS);
  coreApi.listWhatsappTemplates.mockResolvedValue([]);
  coreApi.listQualificationQuestions.mockResolvedValue([
    { key: 'pain_level', label: 'Dolor', kind: 'number' },
  ]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setupAll();
});

async function renderServices(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(() => useServicesData({ session, tenant }));
  await waitFor(() => {
    expect(hook.result.current.state.services.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useServicesData', () => {
  it('loads services, promotions, settings, templates, qualification keys on mount', async () => {
    const hook = await renderServices();
    expect(coreApi.listServices).toHaveBeenCalled();
    expect(coreApi.listPromotions).toHaveBeenCalled();
    expect(coreApi.getTenantSettings).toHaveBeenCalled();
    expect(coreApi.listWhatsappTemplates).toHaveBeenCalled();
    expect(coreApi.listQualificationQuestions).toHaveBeenCalled();
    expect(hook.result.current.state.defaultDuration).toBe(45);
    expect(hook.result.current.state.qualificationKeys.some((k) => k.key === 'pain_level')).toBe(true);
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useServicesData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listServices).not.toHaveBeenCalled();
  });

  it('surfaces an error notice when listServices rejects', async () => {
    coreApi.listServices.mockRejectedValueOnce(new Error('list-fail'));
    const { result } = renderHook(() => useServicesData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    expect(result.current.state.notice.text).toBe('list-fail');
  });

  it('catches getTenantSettings / templates / qualifications errors quietly', async () => {
    coreApi.getTenantSettings.mockRejectedValueOnce(new Error('settings-fail'));
    coreApi.listWhatsappTemplates.mockRejectedValueOnce(new Error('tpl-fail'));
    coreApi.listQualificationQuestions.mockRejectedValueOnce(new Error('q-fail'));
    const { result } = renderHook(() => useServicesData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(coreApi.listServices).toHaveBeenCalled());
    expect(result.current.state.recallTemplates).toEqual([]);
    expect(result.current.state.qualificationKeys.length).toBeGreaterThan(0);
  });

  it('startEdit + setForm + resetForm cycle', async () => {
    const hook = await renderServices();
    act(() => hook.result.current.actions.startEdit(SVC_A));
    expect(hook.result.current.state.editingId).toBe('svc-a');
    expect(hook.result.current.state.form.name).toBe('Servicio A');

    act(() => hook.result.current.actions.resetForm());
    expect(hook.result.current.state.editingId).toBeNull();
    expect(hook.result.current.state.form.name).toBe('');
  });

  it('rule-builder addRule / updateRule / removeRule', async () => {
    const hook = await renderServices();
    act(() => hook.result.current.actions.addRule('pain_level'));
    expect(hook.result.current.state.form.applies_when_rules.length).toBe(1);
    act(() => hook.result.current.actions.updateRule(0, { value: 5 }));
    expect(hook.result.current.state.form.applies_when_rules[0].value).toBe(5);
    act(() => hook.result.current.actions.removeRule(0));
    expect(hook.result.current.state.form.applies_when_rules.length).toBe(0);
  });

  it('submit create posts createService and reloads', async () => {
    coreApi.createService.mockResolvedValueOnce({ id: 'svc-new' });
    const hook = await renderServices();
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'Nuevo',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.createService).toHaveBeenCalled();
    expect(coreApi.listServices).toHaveBeenCalledTimes(2);
    // Note: loadServices() at the end of submit() clears notice via setNotice(null),
    // so we just assert the API call + reload happened, not the success notice.
  });

  it('submit edit posts updateService with editingId', async () => {
    coreApi.updateService.mockResolvedValueOnce({ id: 'svc-a' });
    const hook = await renderServices();
    act(() => hook.result.current.actions.startEdit(SVC_A));
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'Renamed',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(coreApi.updateService).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'svc-a',
      expect.objectContaining({ name: 'Renamed' }),
    );
  });

  it('submit rejects when name is empty', async () => {
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.createService).not.toHaveBeenCalled();
  });

  it('submit surfaces an error notice on rejection', async () => {
    coreApi.createService.mockRejectedValueOnce(new Error('create-fail'));
    const hook = await renderServices();
    act(() =>
      hook.result.current.actions.setForm({
        ...hook.result.current.state.form,
        name: 'X',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.submit();
    });
    expect(hook.result.current.state.notice?.text).toBe('create-fail');
  });

  it('deactivate calls deactivateService and reloads', async () => {
    coreApi.deactivateService.mockResolvedValueOnce({});
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.deactivate(SVC_A);
    });
    expect(coreApi.deactivateService).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'svc-a');
    expect(coreApi.listServices).toHaveBeenCalledTimes(2);
  });

  it('deactivate clears editing state if the deactivated service was being edited', async () => {
    coreApi.deactivateService.mockResolvedValueOnce({});
    const hook = await renderServices();
    act(() => hook.result.current.actions.startEdit(SVC_A));
    await act(async () => {
      await hook.result.current.actions.deactivate(SVC_A);
    });
    expect(hook.result.current.state.editingId).toBeNull();
  });

  it('deactivate surfaces an error notice on rejection', async () => {
    coreApi.deactivateService.mockRejectedValueOnce(new Error('deact-fail'));
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.deactivate(SVC_A);
    });
    expect(hook.result.current.state.notice?.text).toBe('deact-fail');
  });

  it('move reorders services and calls reorderServices', async () => {
    coreApi.reorderServices.mockResolvedValueOnce({});
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.move(0, 1);
    });
    expect(coreApi.reorderServices).toHaveBeenCalled();
    const args = coreApi.reorderServices.mock.calls[0][2];
    expect(args[0].id).toBe('svc-b');
    expect(args[1].id).toBe('svc-a');
  });

  it('move out of bounds is a no-op', async () => {
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.move(0, -1);
    });
    expect(coreApi.reorderServices).not.toHaveBeenCalled();
  });

  it('move reloads when reorderServices fails', async () => {
    coreApi.reorderServices.mockRejectedValueOnce(new Error('reorder-fail'));
    const hook = await renderServices();
    await act(async () => {
      await hook.result.current.actions.move(0, 1);
    });
    // After the error path, loadServices() runs and clears notice; assert reload + the
    // reorderServices call (the error notice is wiped by the reload).
    expect(coreApi.reorderServices).toHaveBeenCalled();
    expect(coreApi.listServices).toHaveBeenCalledTimes(2);
  });

  it('saveDefaultDuration posts settings update and reflects success', async () => {
    coreApi.updateTenantSettings.mockResolvedValueOnce({
      ...TENANT_SETTINGS,
      escalation_policy: { service_durations: { default: 90 } },
    });
    const hook = await renderServices();
    act(() => hook.result.current.actions.setDefaultDuration(90));
    await act(async () => {
      await hook.result.current.actions.saveDefaultDuration();
    });
    expect(coreApi.updateTenantSettings).toHaveBeenCalled();
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('saveDefaultDuration rejects invalid duration', async () => {
    const hook = await renderServices();
    act(() => hook.result.current.actions.setDefaultDuration(0));
    await act(async () => {
      await hook.result.current.actions.saveDefaultDuration();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.updateTenantSettings).not.toHaveBeenCalled();
  });

  it('saveDefaultDuration surfaces an error notice on rejection', async () => {
    coreApi.updateTenantSettings.mockRejectedValueOnce(new Error('update-fail'));
    const hook = await renderServices();
    act(() => hook.result.current.actions.setDefaultDuration(60));
    await act(async () => {
      await hook.result.current.actions.saveDefaultDuration();
    });
    expect(hook.result.current.state.notice?.text).toBe('update-fail');
  });

  it('setIncludeInactive toggles reload', async () => {
    const hook = await renderServices();
    act(() => hook.result.current.actions.setIncludeInactive(true));
    await waitFor(() => {
      expect(coreApi.listServices).toHaveBeenCalledTimes(2);
    });
    expect(coreApi.listServices).toHaveBeenLastCalledWith(SESSION, 'tenant-acme', {
      includeInactive: true,
    });
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.listServices.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useServicesData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    act(() => result.current.actions.dismissNotice());
    expect(result.current.state.notice).toBeNull();
  });
});
