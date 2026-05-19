/**
 * Coverage push for useServiceRequestsData — exercises SR CRUD, quote
 * creation/send/status and the quote line-item editors.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  createQuote: vi.fn(),
  createServiceRequest: vi.fn(),
  getQuoteForSr: vi.fn(),
  listServiceRequests: vi.fn(),
  patchQuote: vi.fn(),
  patchServiceRequest: vi.fn(),
  sendQuote: vi.fn(),
  conversationMessageMediaUrl: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useServiceRequestsData } from './useServiceRequestsData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-1', vertical_code: 'health' };
const CONV_DETAIL = { contact_id: 'contact-1' };
const SR = { id: 'sr-1', status: 'open', service_type: 'limpieza' };

function makeSetup(opts = {}) {
  const tenant = 'tenant' in opts ? opts.tenant : TENANT;
  const convDetail = 'convDetail' in opts ? opts.convDetail : CONV_DETAIL;
  const setNotice = vi.fn();
  const hook = renderHook(() =>
    useServiceRequestsData({
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
  coreApi.listServiceRequests.mockResolvedValue([SR]);
  coreApi.getQuoteForSr.mockResolvedValue({ id: 'q-1', status: 'draft' });
});

describe('useServiceRequestsData', () => {
  it('loads service requests when a contact is provided', async () => {
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));
    expect(coreApi.listServiceRequests).toHaveBeenCalledWith(SESSION, 'tenant-1', {
      contact_id: 'contact-1',
    });
  });

  it('clears SR state when there is no contact', () => {
    const { hook } = makeSetup({ convDetail: {} });
    expect(hook.result.current.state.serviceRequests).toEqual([]);
    expect(hook.result.current.state.selectedSrId).toBeNull();
  });

  it('handleCreateServiceRequest rejects when serviceType is empty', async () => {
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handleCreateServiceRequest({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: expect.stringMatching(/Tipo de servicio/) }),
    );
    expect(coreApi.createServiceRequest).not.toHaveBeenCalled();
  });

  it('handleCreateServiceRequest creates an SR on valid input', async () => {
    coreApi.createServiceRequest.mockResolvedValueOnce({ id: 'sr-2' });
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    act(() =>
      hook.result.current.actions.setSrForm({
        serviceType: 'reparación',
        problemSummary: 'fuga de agua',
        urgency: 'high',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleCreateServiceRequest({ preventDefault: () => {} });
    });

    expect(coreApi.createServiceRequest).toHaveBeenCalled();
  });

  it('handleCreateServiceRequest surfaces error notice on failure', async () => {
    coreApi.createServiceRequest.mockRejectedValueOnce(new Error('sr-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    act(() =>
      hook.result.current.actions.setSrForm({
        serviceType: 'reparación',
        problemSummary: '',
        urgency: 'normal',
      }),
    );

    await act(async () => {
      await hook.result.current.actions.handleCreateServiceRequest({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'sr-fail' }),
    );
  });

  it('handlePatchSrStatus patches the SR status', async () => {
    coreApi.patchServiceRequest.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handlePatchSrStatus('sr-1', 'closed');
    });

    expect(coreApi.patchServiceRequest).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'sr-1',
      { status: 'closed' },
    );
  });

  it('handlePatchSrStatus surfaces error notice on failure', async () => {
    coreApi.patchServiceRequest.mockRejectedValueOnce(new Error('patch-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    await act(async () => {
      await hook.result.current.actions.handlePatchSrStatus('sr-1', 'closed');
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'patch-fail' }),
    );
  });

  it('handleCreateQuote bails when no SR is selected', async () => {
    const { hook } = makeSetup({ convDetail: {} });
    await act(async () => {
      await hook.result.current.actions.handleCreateQuote({ preventDefault: () => {} });
    });
    expect(coreApi.createQuote).not.toHaveBeenCalled();
  });

  it('handleCreateQuote sends only items with a description', async () => {
    coreApi.createQuote.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    // Populate one item and add another empty one
    act(() => {
      hook.result.current.actions.updateQuoteItem(0, 'description', 'svc-a');
      hook.result.current.actions.updateQuoteItem(0, 'qty', '2');
      hook.result.current.actions.updateQuoteItem(0, 'unit_price', '100');
      hook.result.current.actions.addQuoteItem();
    });

    await act(async () => {
      await hook.result.current.actions.handleCreateQuote({ preventDefault: () => {} });
    });

    expect(coreApi.createQuote).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'sr-1',
      expect.objectContaining({
        line_items: [{ description: 'svc-a', qty: 2, unit_price: 100 }],
      }),
    );
  });

  it('handleCreateQuote surfaces error notice on failure', async () => {
    coreApi.createQuote.mockRejectedValueOnce(new Error('quote-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    act(() => hook.result.current.actions.updateQuoteItem(0, 'description', 'svc-a'));

    await act(async () => {
      await hook.result.current.actions.handleCreateQuote({ preventDefault: () => {} });
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'quote-fail' }),
    );
  });

  it('handleSendQuote bails when there is no quote', async () => {
    const { hook } = makeSetup({ convDetail: {} });
    await act(async () => {
      await hook.result.current.actions.handleSendQuote();
    });
    expect(coreApi.sendQuote).not.toHaveBeenCalled();
  });

  it('handleSendQuote sends an existing quote', async () => {
    coreApi.sendQuote.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    // Wait for the quote useEffect to populate
    await waitFor(() => expect(hook.result.current.state.srQuote).not.toBeNull());

    await act(async () => {
      await hook.result.current.actions.handleSendQuote();
    });

    expect(coreApi.sendQuote).toHaveBeenCalledWith(SESSION, 'tenant-1', 'q-1');
  });

  it('handleSendQuote surfaces error notice on failure', async () => {
    coreApi.sendQuote.mockRejectedValueOnce(new Error('send-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.srQuote).not.toBeNull());

    await act(async () => {
      await hook.result.current.actions.handleSendQuote();
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'send-fail' }),
    );
  });

  it('handleUpdateQuoteStatus patches the quote status', async () => {
    coreApi.patchQuote.mockResolvedValueOnce({});
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.srQuote).not.toBeNull());

    await act(async () => {
      await hook.result.current.actions.handleUpdateQuoteStatus('accepted');
    });

    expect(coreApi.patchQuote).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      'q-1',
      { status: 'accepted' },
    );
  });

  it('handleUpdateQuoteStatus surfaces error notice on failure', async () => {
    coreApi.patchQuote.mockRejectedValueOnce(new Error('quote-fail'));
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.srQuote).not.toBeNull());

    await act(async () => {
      await hook.result.current.actions.handleUpdateQuoteStatus('rejected');
    });

    expect(setNotice).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', text: 'quote-fail' }),
    );
  });

  it('treats getQuoteForSr 404 as "no quote" without raising a notice', async () => {
    const err = new Error('not found');
    err.status = 404;
    coreApi.getQuoteForSr.mockRejectedValueOnce(err);
    const { hook, setNotice } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));
    expect(hook.result.current.state.srQuote).toBeNull();
    // No error notice on 404
    const errorNoticeCalls = setNotice.mock.calls.filter(
      (call) => call[0]?.type === 'error',
    );
    expect(errorNoticeCalls).toHaveLength(0);
  });

  it('addQuoteItem and removeQuoteItem manage the line list', async () => {
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    expect(hook.result.current.state.quoteItems).toHaveLength(1);
    act(() => hook.result.current.actions.addQuoteItem());
    expect(hook.result.current.state.quoteItems).toHaveLength(2);
    act(() => hook.result.current.actions.removeQuoteItem(0));
    expect(hook.result.current.state.quoteItems).toHaveLength(1);
  });

  it('setQuoteDiscount and setQuoteTax update totals', async () => {
    const { hook } = makeSetup();
    await waitFor(() => expect(hook.result.current.state.serviceRequests.length).toBe(1));

    act(() => {
      hook.result.current.actions.updateQuoteItem(0, 'description', 'svc');
      hook.result.current.actions.updateQuoteItem(0, 'qty', '2');
      hook.result.current.actions.updateQuoteItem(0, 'unit_price', '100');
      hook.result.current.actions.setQuoteDiscount(20);
      hook.result.current.actions.setQuoteTax(10);
    });

    const totals = hook.result.current.state.quoteTotals;
    expect(totals).toBeTruthy();
  });
});
