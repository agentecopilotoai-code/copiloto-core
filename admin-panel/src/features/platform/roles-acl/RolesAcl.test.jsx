import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { RolesAcl } from './RolesAcl.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

function setup() {
  return render(
    <MemoryRouter>
      <RolesAcl />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
});

describe('RolesAcl', () => {
  it('renders the header, the grouped matrix and the policy panel', () => {
    setup();

    expect(screen.getByRole('heading', { name: 'Roles & ACL' })).toBeInTheDocument();
    // A capability group + a known capability key from PERMISSIONS.
    expect(screen.getByText('Operación diaria')).toBeInTheDocument();
    expect(screen.getByText('conversations.view')).toBeInTheDocument();
    expect(screen.getByText('platform.tenants.read')).toBeInTheDocument();
    // Static policy panel.
    expect(screen.getByText('Política de roles')).toBeInTheDocument();
  });

  it('filters the matrix by capability search', async () => {
    setup();
    expect(screen.getByText('conversations.view')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Buscar capacidad'), 'platform');

    expect(screen.queryByText('conversations.view')).toBeNull();
    expect(screen.getByText('platform.tenants.read')).toBeInTheDocument();
    expect(screen.getByText('Platform Owner · fleet')).toBeInTheDocument();
  });

  it('renders capability-count tiles per role', () => {
    setup();
    // One KPI tile per role — the platform_owner tile exists with a count.
    const tile = screen
      .getByText('Platform Owner', { selector: '.label' })
      .closest('article');
    expect(tile).not.toBeNull();
    expect(tile.textContent).toMatch(/\d/);
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Roles & ACL' })).toBeNull();
  });
});
