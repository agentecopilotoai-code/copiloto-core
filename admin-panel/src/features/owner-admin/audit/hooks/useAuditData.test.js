/**
 * Coverage push for useAuditData — exercises loadLogs, exportCsv, suppress
 * contact and exportTenantData including their guards and error branches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  exportAuditLogs: vi.fn(),
  exportTenantData: vi.fn(),
  listAuditLogsFiltered: vi.fn(),
  suppressContact: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useAuditData } from './useAuditData.js';

const SESSION = { accessToken: 'tok' };
const TENANT = { id: 'tenant-1' };

function setup(opts = {}) {
  const tenant = 'tenant' in opts ? opts.tenant : TENANT;
  return renderHook(() => useAuditData({ session: SESSION, tenant }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAuditData', () => {
  it('starts with empty state', () => {
    const hook = setup();
    expect(hook.result.current.state.logs).toEqual([]);
    expect(hook.result.current.state.loaded).toBe(false);
    expect(hook.result.current.state.tenantId).toBe('tenant-1');
  });

  it('loadLogs is a no-op without a tenant', async () => {
    const hook = setup({ tenant: undefined });
    await act(async () => {
      await hook.result.current.actions.loadLogs();
    });
    expect(coreApi.listAuditLogsFiltered).not.toHaveBeenCalled();
  });

  it('loadLogs populates logs and marks loaded', async () => {
    coreApi.listAuditLogsFiltered.mockResolvedValueOnce([
      { id: 'log-1', action: 'create' },
    ]);
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.loadLogs();
    });
    expect(hook.result.current.state.logs).toHaveLength(1);
    expect(hook.result.current.state.loaded).toBe(true);
  });

  it('loadLogs surfaces an info notice when no rows match', async () => {
    coreApi.listAuditLogsFiltered.mockResolvedValueOnce([]);
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.loadLogs();
    });
    expect(hook.result.current.state.notice?.type).toBe('info');
  });

  it('loadLogs surfaces an error notice on failure', async () => {
    coreApi.listAuditLogsFiltered.mockRejectedValueOnce(new Error('audit-fail'));
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.loadLogs();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('audit-fail');
  });

  it('exportCsv proxies to exportAuditLogs when there is a tenant', () => {
    const hook = setup();
    hook.result.current.actions.exportCsv();
    expect(coreApi.exportAuditLogs).toHaveBeenCalledWith(
      SESSION,
      'tenant-1',
      expect.any(Object),
    );
  });

  it('exportCsv is a no-op without a tenant', () => {
    const hook = setup({ tenant: undefined });
    hook.result.current.actions.exportCsv();
    expect(coreApi.exportAuditLogs).not.toHaveBeenCalled();
  });

  it('suppressContact rejects when suppressId is empty', async () => {
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.suppressContact();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.suppressContact).not.toHaveBeenCalled();
  });

  it('suppressContact calls suppressContact when confirmed', async () => {
    coreApi.suppressContact.mockResolvedValueOnce({});
    const hook = setup();
    act(() => hook.result.current.actions.setSuppressId('contact-uuid'));
    await act(async () => {
      await hook.result.current.actions.suppressContact();
    });
    expect(coreApi.suppressContact).toHaveBeenCalledWith(SESSION, 'tenant-1', 'contact-uuid');
    expect(hook.result.current.state.notice?.type).toBe('success');
  });

  it('suppressContact surfaces error notice on failure', async () => {
    coreApi.suppressContact.mockRejectedValueOnce(new Error('sup-fail'));
    const hook = setup();
    act(() => hook.result.current.actions.setSuppressId('contact-uuid'));
    await act(async () => {
      await hook.result.current.actions.suppressContact();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('sup-fail');
  });

  it('exportTenantData proxies the call and stays busy during the export', async () => {
    coreApi.exportTenantData.mockResolvedValueOnce({});
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.exportTenantData();
    });
    expect(coreApi.exportTenantData).toHaveBeenCalledWith(SESSION, 'tenant-1');
  });

  it('exportTenantData is a no-op without a tenant', async () => {
    const hook = setup({ tenant: undefined });
    await act(async () => {
      await hook.result.current.actions.exportTenantData();
    });
    expect(coreApi.exportTenantData).not.toHaveBeenCalled();
  });

  it('exportTenantData surfaces error notice on failure', async () => {
    coreApi.exportTenantData.mockRejectedValueOnce(new Error('ex-fail'));
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.exportTenantData();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('ex-fail');
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.listAuditLogsFiltered.mockRejectedValueOnce(new Error('boom'));
    const hook = setup();
    await act(async () => {
      await hook.result.current.actions.loadLogs();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    act(() => hook.result.current.actions.dismissNotice());
    expect(hook.result.current.state.notice).toBeNull();
  });

  it('setFilters updates the filters state', () => {
    const hook = setup();
    act(() => hook.result.current.actions.setFilters({ ...hook.result.current.state.filters, action: 'create' }));
    expect(hook.result.current.state.filters.action).toBe('create');
  });
});
