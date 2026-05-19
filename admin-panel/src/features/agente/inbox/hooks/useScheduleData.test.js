/**
 * Coverage push for useScheduleData — exercises the resource CRUD,
 * appointment scheduling/cancel and payment-link branches plus the
 * validation guards that short-circuit each handler.
 *
 * The hook fires many coreApi calls on mount (refreshScheduleData +
 * loadCalendar). We mock everything to resolve to empty arrays so the
 * mount doesn't blow up, then assert the handler-level behaviour.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  cancelAppointment: vi.fn(),
  createAppointment: vi.fn(),
  createResource: vi.fn(),
  generateAppointmentPaymentLink: vi.fn(),
  getTenantAvailability: vi.fn(),
  listAppointmentFeedback: vi.fn(),
  listAppointments: vi.fn(),
  listMediaAssets: vi.fn(),
  listResources: vi.fn(),
  sendAppointmentPaymentLink: vi.fn(),
  updateAppointment: vi.fn(),
  updateAppointmentPaymentStatus: vi.fn(),
  updateResource: vi.fn(),
  conversationMessageMediaUrl: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useScheduleData } from './useScheduleData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-1', vertical_code: 'health' };
const CONV_DETAIL = { contact_id: 'contact-1' };
const RESOURCE = { id: 'res-1', code: 'r1', name: 'Recurso 1' };
const APPOINTMENT = { id: 'ap-1', payment_amount: 5000, payment_currency: 'COP' };

function makeSetup(opts = {}) {
  const tenant = 'tenant' in opts ? opts.tenant : TENANT;
  const convDetail = 'convDetail' in opts ? opts.convDetail : CONV_DETAIL;
  const setNotice = vi.fn();
  const hook = renderHook(() =>
    useScheduleData({
      session: SESSION,
      tenant,
      conversationDetail: convDetail,
      selectedConversationId: 'conv-1',
      setNotice,
    }),
  );
  return { hook, setNotice };
}

beforeEach(() => {
  vi.clearAllMocks();
  coreApi.listMediaAssets.mockResolvedValue([]);
  coreApi.listResources.mockResolvedValue([RESOURCE]);
  coreApi.listAppointments.mockResolvedValue([APPOINTMENT]);
  coreApi.listAppointmentFeedback.mockResolvedValue([{ rating: 5 }]);
  coreApi.getTenantAvailability.mockResolvedValue({ slots: [] });
});

describe('useScheduleData', () => {
  it('mounts and loads resources + appointments + calendar', async () => {
    const { hook } = makeSetup();
    await waitFor(() => {
      expect(hook.result.current.state.resources.length).toBe(1);
    });
    expect(coreApi.listResources).toHaveBeenCalled();
    expect(coreApi.listAppointments).toHaveBeenCalled();
    expect(coreApi.getTenantAvailability).toHaveBeenCalled();
  });

  it('does not crash when there is no tenant on mount', () => {
    const { hook } = makeSetup({ tenant: undefined });
    expect(hook.result.current.state.resources).toEqual([]);
  });

  it('handleCreateResource rejects empty code/name', async () => {
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleCreateResource({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: expect.stringMatching(/Código y nombre/) }),
    );
    expect(coreApi.createResource).not.toHaveBeenCalled();
  });

  it('handleCreateResource creates a new resource when not editing', async () => {
    coreApi.createResource.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() => {
      hook.result.current.actions.setResourceForm({
        ...hook.result.current.state.resourceForm,
        code: 'r2',
        name: 'Recurso 2',
      });
    });

    await act(async () => {
      await hook.result.current.actions.handleCreateResource({ preventDefault: () => {} });
    });

    expect(coreApi.createResource).toHaveBeenCalled();
  });

  it('handleEditResource hydrates the form from the record', async () => {
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() => hook.result.current.actions.handleEditResource(RESOURCE));
    expect(hook.result.current.state.editingResourceId).toBe('res-1');
    expect(hook.result.current.state.resourceForm.code).toBe('r1');
  });

  it('handleCancelResourceEdit resets the editing state', async () => {
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() => hook.result.current.actions.handleEditResource(RESOURCE));
    expect(hook.result.current.state.editingResourceId).toBe('res-1');

    act(() => hook.result.current.actions.handleCancelResourceEdit());
    expect(hook.result.current.state.editingResourceId).toBeNull();
  });

  it('handleCreateResource updates an existing resource when editing', async () => {
    coreApi.updateResource.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() => hook.result.current.actions.handleEditResource(RESOURCE));
    await act(async () => {
      await hook.result.current.actions.handleCreateResource({ preventDefault: () => {} });
    });
    expect(coreApi.updateResource).toHaveBeenCalled();
  });

  it('handleCreateResource surfaces error notice when API throws', async () => {
    coreApi.createResource.mockRejectedValueOnce(new Error('boom'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() => {
      hook.result.current.actions.setResourceForm({
        ...hook.result.current.state.resourceForm,
        code: 'r2',
        name: 'Recurso 2',
      });
    });

    await act(async () => {
      await hook.result.current.actions.handleCreateResource({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'boom' }),
    );
  });

  it('handleCreateAppointment rejects when required fields are missing', async () => {
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleCreateAppointment({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: expect.stringMatching(/Selecciona conversación/) }),
    );
    expect(coreApi.createAppointment).not.toHaveBeenCalled();
  });

  it('handleCreateAppointment creates an appointment when form is complete', async () => {
    coreApi.createAppointment.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() =>
      hook.result.current.actions.setAppointmentForm({
        resourceId: 'res-1',
        serviceCode: 'svc-1',
        startsAt: '2026-05-20T10:00',
        endsAt: '2026-05-20T11:00',
        notes: 'note',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleCreateAppointment({ preventDefault: () => {} });
    });

    expect(coreApi.createAppointment).toHaveBeenCalled();
  });

  it('handleCreateAppointment handles api error', async () => {
    coreApi.createAppointment.mockRejectedValueOnce(new Error('conflict'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() =>
      hook.result.current.actions.setAppointmentForm({
        resourceId: 'res-1',
        serviceCode: 'svc-1',
        startsAt: '2026-05-20T10:00',
        endsAt: '2026-05-20T11:00',
        notes: '',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleCreateAppointment({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'conflict' }),
    );
  });

  it('handleRescheduleAppointment rejects when form is incomplete', async () => {
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleRescheduleAppointment({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' }),
    );
    expect(coreApi.updateAppointment).not.toHaveBeenCalled();
  });

  it('handleRescheduleAppointment updates the appointment when form is complete', async () => {
    coreApi.updateAppointment.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() =>
      hook.result.current.actions.setRescheduleForm({
        appointmentId: 'ap-1',
        resourceId: 'res-1',
        startsAt: '2026-05-20T10:00',
        endsAt: '2026-05-20T11:00',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleRescheduleAppointment({ preventDefault: () => {} });
    });

    expect(coreApi.updateAppointment).toHaveBeenCalled();
  });

  it('handleCancelAppointment calls cancelAppointment and refreshes', async () => {
    coreApi.cancelAppointment.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleCancelAppointment('ap-1');
    });

    expect(coreApi.cancelAppointment).toHaveBeenCalledWith(SESSION, 'tenant-1', 'ap-1');
  });

  it('handleCancelAppointment surfaces error notice on failure', async () => {
    coreApi.cancelAppointment.mockRejectedValueOnce(new Error('no-cancel'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleCancelAppointment('ap-1');
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'no-cancel' }),
    );
  });

  it('handleGeneratePaymentLink rejects amount <= 0', async () => {
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() =>
      hook.result.current.actions.setPaymentDrafts({ 'ap-1': { amount: '0' } }),
    );

    await act(async () => {
      await hook.result.current.actions.handleGeneratePaymentLink({ id: 'ap-1' });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: expect.stringMatching(/monto mayor a 0/) }),
    );
    expect(coreApi.generateAppointmentPaymentLink).not.toHaveBeenCalled();
  });

  it('handleGeneratePaymentLink generates with the draft amount + currency', async () => {
    coreApi.generateAppointmentPaymentLink.mockResolvedValueOnce({ payment_url: 'https://pay' });
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    act(() =>
      hook.result.current.actions.setPaymentDrafts({
        'ap-1': { amount: '12000', currency: 'USD', description: 'consulta' },
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleGeneratePaymentLink(APPOINTMENT);
    });

    expect(coreApi.generateAppointmentPaymentLink).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'ap-1',
      { amount: 12000, currency: 'USD', description: 'consulta' },
    );
  });

  it('handleSendPaymentLink sends and applies summary', async () => {
    coreApi.sendAppointmentPaymentLink.mockResolvedValueOnce({ payment_status: 'link_sent' });
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleSendPaymentLink('ap-1');
    });

    expect(coreApi.sendAppointmentPaymentLink).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'ap-1',
    );
  });

  it('handleSendPaymentLink surfaces error notice on failure', async () => {
    coreApi.sendAppointmentPaymentLink.mockRejectedValueOnce(new Error('send-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleSendPaymentLink('ap-1');
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'send-fail' }),
    );
  });

  it('handleMarkPaymentStatus updates the appointment status', async () => {
    coreApi.updateAppointmentPaymentStatus.mockResolvedValueOnce({ payment_status: 'paid' });
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleMarkPaymentStatus('ap-1', 'paid');
    });

    expect(coreApi.updateAppointmentPaymentStatus).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'ap-1',
      { payment_status: 'paid' },
    );
  });

  it('loadCalendar surfaces error notice when availability fetch fails', async () => {
    coreApi.getTenantAvailability.mockRejectedValueOnce(new Error('no-avail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.resources.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.loadCalendar('2026-05-20');
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'no-avail' }),
    );
  });
});
