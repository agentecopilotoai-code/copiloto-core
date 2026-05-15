import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

// Stub coreApi para evitar arrastrar el módulo real (mismo patrón que el test
// funcional de FleetTenants).
vi.mock('../../services/coreApi.js', () => ({
  listFleetTenants: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { listFleetTenants } from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { FleetTenants } from '../../features/platform/fleet-tenants/index.js';

const PLATFORM_OWNER = {
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
];

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER },
    profile: PLATFORM_OWNER,
    handleTenantCreated: vi.fn(),
  };
  listFleetTenants.mockResolvedValue({
    items: TENANTS,
    total: TENANTS.length,
    limit: 100,
    offset: 0,
  });
});

describe('a11y · Platform · Fleet · Tenants', () => {
  it('a11y — Tenants list has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <FleetTenants />
      </MemoryRouter>,
    );
    // Esperar a que cargue antes de auditar (sin tabla, axe no ve el grueso del DOM).
    await screen.findByText('Clínica Estética Norte');

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
