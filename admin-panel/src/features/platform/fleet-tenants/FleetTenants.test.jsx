import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listFleetTenants: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockHandleTenantCreated = vi.fn();
let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { listFleetTenants } from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { FleetTenants } from './FleetTenants.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const TENANTS = [
  {
    id: 'tenant-1',
    slug: 'clinica-norte',
    legal_name: 'Clínica Norte SAS',
    display_name: 'Clínica Estética Norte',
    vertical_code: 'aesthetic',
    business_type_label: 'Clínica estética',
    country_code: 'CO',
    timezone: 'America/Bogota',
    status: 'active',
    member_count: 8,
    owner_count: 1,
    owner_email: 'owner@clinica-norte.example',
    created_at: '2025-09-01T10:00:00Z',
    updated_at: '2026-04-30T18:00:00Z',
    last_activity_at: '2026-04-30T18:00:00Z',
  },
  {
    id: 'tenant-2',
    slug: 'spa-mvd',
    legal_name: 'Spa Montevideo',
    display_name: 'Spa Montevideo',
    vertical_code: 'spa',
    business_type_label: 'Spa',
    country_code: 'UY',
    timezone: 'America/Montevideo',
    status: 'trial',
    member_count: 2,
    owner_count: 0,
    owner_email: null,
    created_at: '2026-04-01T08:00:00Z',
    updated_at: '2026-04-12T08:00:00Z',
    last_activity_at: '2026-04-12T08:00:00Z',
  },
];

function setup() {
  return render(
    <MemoryRouter>
      <FleetTenants />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
    handleTenantCreated: mockHandleTenantCreated,
    // BUG-008 — handleSupportInto ahora activa support_mode antes de navegar.
    activateSupportMode: vi.fn().mockResolvedValue({
      tenant_id: 'any',
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      ttl_seconds: 3600,
    }),
    deactivateSupportMode: vi.fn().mockResolvedValue(undefined),
    supportModeOverride: null,
  };
  listFleetTenants.mockResolvedValue({ items: TENANTS, total: TENANTS.length, limit: 100, offset: 0 });
});

describe('FleetTenants', () => {
  it('renders the header and KPIs from the fleet snapshot', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Fleet · Tenants' }),
    ).toBeInTheDocument();

    // KPI labels present (the values may collide with table cells, so query the
    // tile element by its label and then assert against its sibling).
    const activeKpi = screen.getByText('Tenants activos').closest('article');
    expect(activeKpi).not.toBeNull();
    expect(activeKpi.textContent).toContain('1'); // 1 active tenant in TENANTS

    const countriesKpi = screen.getByText('Países cubiertos').closest('article');
    expect(countriesKpi).not.toBeNull();
    expect(countriesKpi.textContent).toContain('2'); // CO + UY

    // Tenants render in the table
    expect(screen.getByText('Clínica Estética Norte')).toBeInTheDocument();
    expect(screen.getByText('Spa Montevideo')).toBeInTheDocument();
    expect(screen.getByText('owner@clinica-norte.example')).toBeInTheDocument();
    expect(screen.getByText('Sin owner')).toBeInTheDocument();
  });

  it('passes the documented filter set to the endpoint', async () => {
    setup();
    await screen.findByText('Clínica Estética Norte');

    listFleetTenants.mockClear();
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'active');

    await waitFor(() => {
      expect(listFleetTenants).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ status: 'active', limit: 100, offset: 0 }),
      );
    });
  });

  it('opens the drawer with tenant detail on row click and navigates on "Ver como tenant"', async () => {
    setup();
    await screen.findByText('Clínica Estética Norte');

    await userEvent.click(screen.getByText('Clínica Estética Norte'));

    // Drawer opens as a dialog; scope detail assertions to it so we don't
    // collide with the same strings rendered in the underlying table row.
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('clinica-norte');
    expect(dialog.textContent).toContain('aesthetic');
    expect(dialog.textContent).toContain('owner@clinica-norte.example');

    await userEvent.click(screen.getByRole('button', { name: 'Ver como tenant' }));

    expect(mockHandleTenantCreated).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'tenant-1', slug: 'clinica-norte' }),
    );
    expect(mockNavigate).toHaveBeenCalledWith('/t/clinica-norte');
  });

  it('renders an error state when the API call fails and supports retry', async () => {
    listFleetTenants.mockRejectedValueOnce(new Error('Network down'));
    setup();

    expect(await screen.findByText('No se pudo cargar la flota')).toBeInTheDocument();
    expect(screen.getByText('Network down')).toBeInTheDocument();

    listFleetTenants.mockResolvedValueOnce({ items: TENANTS, total: 2, limit: 100, offset: 0 });
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await screen.findByText('Clínica Estética Norte');
  });

  it('hides AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
      handleTenantCreated: mockHandleTenantCreated,
      activateSupportMode: vi.fn(),
      deactivateSupportMode: vi.fn(),
      supportModeOverride: null,
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Fleet · Tenants' })).toBeNull();
  });
});
