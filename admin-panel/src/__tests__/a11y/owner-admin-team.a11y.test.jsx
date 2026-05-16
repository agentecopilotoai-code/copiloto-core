import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

vi.mock('../../services/coreApi.js', () => ({
  listTenantMembers: vi.fn(),
  inviteTenantMember: vi.fn(),
  updateTenantMemberRole: vi.fn(),
  removeTenantMember: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { TeamModule } from '../../features/owner-admin/team/index.js';

const OWNER_PROFILE = { sub: 'u-owner', roles: ['owner'] };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok', profile: OWNER_PROFILE };
const MODULE = { label: 'Equipo', summary: 'Miembros del tenant' };

const MEMBERS = {
  auth0_management_enabled: true,
  members: [
    {
      user_id: 'u-1',
      email: 'camila@acme.co',
      display_name: 'Camila Rojas',
      roles: ['owner'],
      status: 'active',
      last_login_at: '2026-05-14T10:00:00Z',
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listTenantMembers.mockResolvedValue(MEMBERS);
});

describe('a11y · Owner/Admin · Equipo', () => {
  it('a11y — Team tab has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <TeamModule module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    await screen.findByText('Camila Rojas');

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
