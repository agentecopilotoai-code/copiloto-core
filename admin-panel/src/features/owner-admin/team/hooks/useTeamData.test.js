/**
 * Coverage push for useTeamData — exercises every mutation handler
 * (invite/changeRole/removeMember) plus the error branches the
 * existing TeamModule.test.jsx leaves on the table.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('../../../../services/coreApi.js', () => ({
  listTenantMembers: vi.fn(),
  inviteTenantMember: vi.fn(),
  updateTenantMemberRole: vi.fn(),
  removeTenantMember: vi.fn(),
}));

 
import * as coreApi from '../../../../services/coreApi.js';
 
import { useTeamData } from './useTeamData.js';

const SESSION = { accessToken: 'tok', profile: { sub: 'u-owner', roles: ['owner'] } };
const TENANT = { id: 'tenant-acme', roles: ['owner'] };

const MEMBER = {
  user_id: 'u-1',
  email: 'carla@acme.co',
  display_name: 'Carla R.',
  roles: ['agent'],
  status: 'active',
};

function setupMembers() {
  coreApi.listTenantMembers.mockResolvedValue({
    auth0_management_enabled: true,
    members: [MEMBER],
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  setupMembers();
});

async function renderTeam(opts = {}) {
  const { session = SESSION, tenant = TENANT } = opts;
  const hook = renderHook(({ s, t }) => useTeamData({ session: s, tenant: t }), {
    initialProps: { s: session, t: tenant },
  });
  // wait for the initial fetch to land
  await waitFor(() => {
    expect(hook.result.current.state.members.length).toBeGreaterThan(0);
  });
  return hook;
}

describe('useTeamData', () => {
  it('loads members and sets auth0Enabled on mount', async () => {
    const hook = await renderTeam();
    expect(hook.result.current.state.auth0Enabled).toBe(true);
    expect(hook.result.current.state.isOwner).toBe(true);
    expect(coreApi.listTenantMembers).toHaveBeenCalledWith(SESSION, 'tenant-acme');
  });

  it('does not fetch when there is no tenant', () => {
    renderHook(() => useTeamData({ session: SESSION, tenant: undefined }));
    expect(coreApi.listTenantMembers).not.toHaveBeenCalled();
  });

  it('surfaces an error notice when listTenantMembers fails', async () => {
    coreApi.listTenantMembers.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useTeamData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    expect(result.current.state.notice.text).toBe('boom');
  });

  it('opens and closes the invite drawer', async () => {
    const hook = await renderTeam();
    act(() => hook.result.current.actions.openInvite());
    expect(hook.result.current.state.inviteOpen).toBe(true);
    act(() => hook.result.current.actions.closeInvite());
    expect(hook.result.current.state.inviteOpen).toBe(false);
  });

  it('rejects an invite with empty email', async () => {
    const hook = await renderTeam();
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.inviteTenantMember).not.toHaveBeenCalled();
  });

  it('invites a new user and calls inviteTenantMember + refresh', async () => {
    coreApi.inviteTenantMember.mockResolvedValueOnce({
      auth0: { invited: true },
    });
    const hook = await renderTeam();
    act(() =>
      hook.result.current.actions.setInviteForm({
        email: 'new@acme.co',
        display_name: 'New One',
        role: 'agent',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(coreApi.inviteTenantMember).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      { email: 'new@acme.co', display_name: 'New One', role: 'agent' },
    );
    // refresh() is called after a successful invite
    expect(coreApi.listTenantMembers).toHaveBeenCalledTimes(2);
    expect(hook.result.current.state.inviteOpen).toBe(false);
  });

  it('hits the "reused existing" success branch when invite returns reused_existing', async () => {
    coreApi.inviteTenantMember.mockResolvedValueOnce({
      auth0: { reused_existing: true },
    });
    const hook = await renderTeam();
    act(() =>
      hook.result.current.actions.setInviteForm({
        email: 'reused@acme.co',
        display_name: '',
        role: 'agent',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(coreApi.inviteTenantMember).toHaveBeenCalledTimes(1);
  });

  it('hits the "auth0 skipped" branch when auth0_skipped is set', async () => {
    coreApi.inviteTenantMember.mockResolvedValueOnce({ auth0_skipped: true });
    const hook = await renderTeam();
    act(() =>
      hook.result.current.actions.setInviteForm({
        email: 'x@acme.co',
        display_name: '',
        role: 'agent',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(coreApi.inviteTenantMember).toHaveBeenCalledTimes(1);
  });

  it('hits the plain "Miembro agregado" branch when no flags are present', async () => {
    coreApi.inviteTenantMember.mockResolvedValueOnce({});
    const hook = await renderTeam();
    act(() =>
      hook.result.current.actions.setInviteForm({
        email: 'plain@acme.co',
        display_name: '',
        role: 'agent',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(coreApi.inviteTenantMember).toHaveBeenCalledTimes(1);
  });

  it('surfaces an error notice when invite throws', async () => {
    coreApi.inviteTenantMember.mockRejectedValueOnce(new Error('invite-fail'));
    const hook = await renderTeam();
    act(() =>
      hook.result.current.actions.setInviteForm({
        email: 'x@acme.co',
        display_name: '',
        role: 'agent',
      }),
    );
    await act(async () => {
      await hook.result.current.actions.invite();
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('invite-fail');
  });

  it('refuses owner promotion when caller is not an owner', async () => {
    const hook = await renderTeam({
      session: { profile: { sub: 'u-x', roles: [] } },
      tenant: { id: 'tenant-acme', roles: ['agent'] },
    });
    await act(async () => {
      await hook.result.current.actions.changeRole(MEMBER, 'owner');
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(coreApi.updateTenantMemberRole).not.toHaveBeenCalled();
  });

  it('updates a member role on confirm and triggers refresh', async () => {
    coreApi.updateTenantMemberRole.mockResolvedValueOnce({});
    const hook = await renderTeam();
    await act(async () => {
      await hook.result.current.actions.changeRole(MEMBER, 'manager');
    });
    expect(coreApi.updateTenantMemberRole).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'u-1',
      'manager',
    );
    expect(coreApi.listTenantMembers).toHaveBeenCalledTimes(2);
  });

  it('surfaces an error notice when updateTenantMemberRole fails', async () => {
    coreApi.updateTenantMemberRole.mockRejectedValueOnce(new Error('role-fail'));
    const hook = await renderTeam();
    await act(async () => {
      await hook.result.current.actions.changeRole(MEMBER, 'manager');
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('role-fail');
  });

  it('removes a member on confirm and triggers refresh', async () => {
    coreApi.removeTenantMember.mockResolvedValueOnce({});
    const hook = await renderTeam();
    await act(async () => {
      await hook.result.current.actions.removeMember(MEMBER);
    });
    expect(coreApi.removeTenantMember).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'u-1',
    );
    expect(coreApi.listTenantMembers).toHaveBeenCalledTimes(2);
  });

  it('surfaces an error notice when removeTenantMember fails', async () => {
    coreApi.removeTenantMember.mockRejectedValueOnce(new Error('remove-fail'));
    const hook = await renderTeam();
    await act(async () => {
      await hook.result.current.actions.removeMember(MEMBER);
    });
    expect(hook.result.current.state.notice?.type).toBe('error');
    expect(hook.result.current.state.notice.text).toBe('remove-fail');
  });

  it('dismissNotice clears the notice', async () => {
    coreApi.listTenantMembers.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useTeamData({ session: SESSION, tenant: TENANT }));
    await waitFor(() => expect(result.current.state.notice?.type).toBe('error'));
    act(() => result.current.actions.dismissNotice());
    expect(result.current.state.notice).toBeNull();
  });
});
