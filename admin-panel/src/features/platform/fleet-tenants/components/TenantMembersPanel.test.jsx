import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../services/coreApi.js', () => ({
  listTenantMembers: vi.fn(),
  inviteTenantMember: vi.fn(),
  updateTenantMemberRole: vi.fn(),
  removeTenantMember: vi.fn(),
}));

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../../../../services/coreApi.js';
import { TenantMembersPanel } from './TenantMembersPanel.jsx';

const SESSION = { accessToken: 'tk' };
const TENANT = { id: 't1', slug: 'acme', display_name: 'Acme' };

beforeEach(() => {
  coreApi.listTenantMembers.mockReset();
  coreApi.inviteTenantMember.mockReset();
  coreApi.updateTenantMemberRole.mockReset();
  coreApi.removeTenantMember.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('<TenantMembersPanel/>', () => {
  it('pinta empty state cuando no hay miembros', async () => {
    coreApi.listTenantMembers.mockResolvedValue({ items: [] });
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    expect(await screen.findByText('Sin miembros')).toBeInTheDocument();
  });

  it('pinta tabla cuando hay miembros', async () => {
    coreApi.listTenantMembers.mockResolvedValue({
      items: [
        {
          user_id: 'u1',
          email: 'a@b.co',
          display_name: 'Alice',
          roles: ['admin'],
          mfa_enabled: true,
          last_login_at: '2026-05-20T10:00:00Z',
        },
      ],
    });
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    expect(await screen.findByTestId('members-table')).toBeInTheDocument();
    expect(screen.getByText('a@b.co')).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('handlea response sin items', async () => {
    coreApi.listTenantMembers.mockResolvedValue({});
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    expect(await screen.findByText('Sin miembros')).toBeInTheDocument();
  });

  it('muestra error si listTenantMembers falla', async () => {
    coreApi.listTenantMembers.mockRejectedValue(new Error('nope'));
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('nope');
  });

  it('invita miembro nuevo y refresca lista', async () => {
    coreApi.listTenantMembers
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({
        items: [{ user_id: 'u-new', email: 'new@b.co', roles: ['admin'] }],
      });
    coreApi.inviteTenantMember.mockResolvedValue({});
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByText('Sin miembros');
    await userEvent.type(screen.getByTestId('add-member-email'), 'NEW@b.co');
    await userEvent.click(screen.getByTestId('add-member-submit'));
    await waitFor(() => {
      expect(coreApi.inviteTenantMember).toHaveBeenCalledWith(
        SESSION,
        't1',
        { email: 'new@b.co', role: 'admin' },
      );
    });
    expect(await screen.findByText('new@b.co')).toBeInTheDocument();
  });

  it('muestra error si invite falla', async () => {
    coreApi.listTenantMembers.mockResolvedValue({ items: [] });
    coreApi.inviteTenantMember.mockRejectedValue(new Error('email ya invitado'));
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByText('Sin miembros');
    await userEvent.type(screen.getByTestId('add-member-email'), 'x@b.co');
    await userEvent.click(screen.getByTestId('add-member-submit'));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('email ya invitado');
    });
  });

  it('cambia rol via select', async () => {
    coreApi.listTenantMembers
      .mockResolvedValueOnce({
        items: [{ user_id: 'u1', email: 'a@b.co', roles: ['admin'] }],
      })
      .mockResolvedValueOnce({
        items: [{ user_id: 'u1', email: 'a@b.co', roles: ['manager'] }],
      });
    coreApi.updateTenantMemberRole.mockResolvedValue({});
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    await userEvent.selectOptions(
      screen.getByTestId('member-role-a@b.co'),
      'manager',
    );
    await waitFor(() => {
      expect(coreApi.updateTenantMemberRole).toHaveBeenCalledWith(
        SESSION, 't1', 'u1', 'manager',
      );
    });
  });

  it('muestra error si cambio de rol falla', async () => {
    coreApi.listTenantMembers.mockResolvedValue({
      items: [{ user_id: 'u1', email: 'a@b.co', roles: ['admin'] }],
    });
    coreApi.updateTenantMemberRole.mockRejectedValue(new Error('forbidden'));
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    await userEvent.selectOptions(screen.getByTestId('member-role-a@b.co'), 'viewer');
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('forbidden');
    });
  });

  it('revoca miembro cuando se confirma el window.confirm', async () => {
    coreApi.listTenantMembers
      .mockResolvedValueOnce({
        items: [{ user_id: 'u1', email: 'a@b.co', roles: ['admin'] }],
      })
      .mockResolvedValueOnce({ items: [] });
    coreApi.removeTenantMember.mockResolvedValue(null);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    await userEvent.click(screen.getByTestId('member-remove-a@b.co'));
    await waitFor(() => {
      expect(coreApi.removeTenantMember).toHaveBeenCalledWith(SESSION, 't1', 'u1');
    });
    expect(await screen.findByText('Sin miembros')).toBeInTheDocument();
  });

  it('cancela revocar cuando el confirm devuelve false', async () => {
    coreApi.listTenantMembers.mockResolvedValue({
      items: [{ user_id: 'u1', email: 'a@b.co', roles: ['admin'] }],
    });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    await userEvent.click(screen.getByTestId('member-remove-a@b.co'));
    expect(coreApi.removeTenantMember).not.toHaveBeenCalled();
  });

  it('muestra error si revoke falla', async () => {
    coreApi.listTenantMembers.mockResolvedValue({
      items: [{ user_id: 'u1', email: 'a@b.co', roles: ['admin'] }],
    });
    coreApi.removeTenantMember.mockRejectedValue(new Error('locked'));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    await userEvent.click(screen.getByTestId('member-remove-a@b.co'));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('locked');
    });
  });

  it('no-op cuando session o tenant.id no están', () => {
    render(<TenantMembersPanel session={null} tenant={TENANT} />);
    expect(coreApi.listTenantMembers).not.toHaveBeenCalled();
  });

  it('handlea miembros con role (singular) en vez de roles[]', async () => {
    coreApi.listTenantMembers.mockResolvedValue({
      items: [{ user_id: 'u1', email: 'a@b.co', role: 'viewer' }],
    });
    render(<TenantMembersPanel session={SESSION} tenant={TENANT} />);
    await screen.findByTestId('members-table');
    expect(screen.getByTestId('member-role-a@b.co').value).toBe('viewer');
  });
});
