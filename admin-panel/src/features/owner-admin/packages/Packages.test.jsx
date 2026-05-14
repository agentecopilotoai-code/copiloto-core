import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listTreatmentPackages: vi.fn(),
  listServices: vi.fn(),
  createTreatmentPackage: vi.fn(),
  updateTreatmentPackage: vi.fn(),
  deactivateTreatmentPackage: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Packages } from './Packages.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Paquetes', summary: 'Planes multi-cita' };

const PACKAGES = [
  {
    id: 'pkg-1',
    name: 'Plan limpieza facial',
    total_sessions: 3,
    validity_days: 90,
    price_amount: 420000,
    price_currency: 'COP',
    includes_service_ids: [],
    is_active: true,
  },
  {
    id: 'pkg-2',
    name: 'Bono botox',
    total_sessions: 4,
    validity_days: 180,
    price_amount: 1280000,
    price_currency: 'COP',
    includes_service_ids: ['s-1'],
    is_active: false,
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <Packages module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listTreatmentPackages.mockResolvedValue(PACKAGES);
  coreApi.listServices.mockResolvedValue([{ id: 's-1', name: 'Limpieza facial' }]);
});

describe('Packages', () => {
  it('renders the catalogue table with active and inactive packages', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Paquetes', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Plan limpieza facial')).toBeInTheDocument();
    expect(screen.getByText('Bono botox')).toBeInTheDocument();
    expect(screen.getByText('Inactivo')).toBeInTheDocument();
  });

  it('opens the create modal from the page header CTA', async () => {
    setup();
    await screen.findByText('Plan limpieza facial');

    await userEvent.click(screen.getByRole('button', { name: 'Nuevo paquete' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nuevo paquete');
    expect(screen.getByRole('button', { name: 'Crear paquete' })).toBeInTheDocument();
  });

  it('opens the edit modal pre-filled when a row is edited', async () => {
    setup();
    await screen.findByText('Plan limpieza facial');

    await userEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Editar paquete');
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks packages.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Paquetes', level: 1 })).toBeNull();
  });
});
