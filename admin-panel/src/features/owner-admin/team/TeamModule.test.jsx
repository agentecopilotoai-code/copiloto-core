import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listTenantMembers: vi.fn(),
  inviteTenantMember: vi.fn(),
  updateTenantMemberRole: vi.fn(),
  removeTenantMember: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { TeamModule } from './TeamModule.jsx';

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
    {
      user_id: 'u-2',
      email: 'luis@acme.co',
      display_name: 'Luis Rivas',
      roles: ['agent'],
      status: 'invited',
      last_login_at: null,
    },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <TeamModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listTenantMembers.mockResolvedValue(MEMBERS);
});

describe('TeamModule', () => {
  it('renders the role-count tiles and the members table', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Equipo', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Camila Rojas')).toBeInTheDocument();
    expect(screen.getByText('Luis Rivas')).toBeInTheDocument();
    expect(screen.getByText('Miembros (2)')).toBeInTheDocument();
    // One pending invite is counted in the tiles.
    expect(screen.getByText('Pendientes')).toBeInTheDocument();
  });

  it('opens the invite drawer from the header CTA', async () => {
    setup();
    await screen.findByText('Camila Rojas');

    await userEvent.click(screen.getByRole('button', { name: 'Invitar miembro' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Invitar miembro');
    expect(screen.getByRole('button', { name: 'Invitar' })).toBeInTheDocument();
  });

  it('filters the members table by the search box', async () => {
    setup();
    await screen.findByText('Camila Rojas');

    await userEvent.type(screen.getByLabelText('Buscar miembros'), 'luis');

    expect(screen.getByText('Luis Rivas')).toBeInTheDocument();
    expect(screen.queryByText('Camila Rojas')).toBeNull();
  });

  it('renders AccessDenied when the active tenant role lacks team.write', () => {
    mockTenantContext = { session: SESSION, profile: { sub: 'u-x' } };
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Equipo', level: 1 })).toBeNull();
  });
});
