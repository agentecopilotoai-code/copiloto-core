import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listServices: vi.fn(),
  listPromotions: vi.fn(),
  getTenantSettings: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  listQualificationQuestions: vi.fn(),
  createService: vi.fn(),
  updateService: vi.fn(),
  deactivateService: vi.fn(),
  reorderServices: vi.fn(),
  updateTenantSettings: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Services } from './Services.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', label: 'Acme · acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Servicios', summary: 'Catálogo' };

const SERVICES = [
  {
    id: 's-1',
    name: 'Limpieza facial',
    category: 'Estética',
    price_amount: 120000,
    price_currency: 'COP',
    duration_minutes: 50,
    recall_interval_days: 90,
    is_active: true,
  },
  {
    id: 's-2',
    name: 'Botox',
    category: 'Estética',
    price_amount: 380000,
    price_currency: 'COP',
    duration_minutes: 30,
    is_active: true,
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <Services module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listServices.mockResolvedValue(SERVICES);
  coreApi.listPromotions.mockResolvedValue([]);
  coreApi.getTenantSettings.mockResolvedValue({ escalation_policy: {} });
  coreApi.listWhatsappTemplates.mockResolvedValue([]);
  coreApi.listQualificationQuestions.mockResolvedValue([]);
});

describe('Services', () => {
  it('renders the catalogue table and the create form for an owner', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Servicios', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Limpieza facial')).toBeInTheDocument();
    expect(screen.getByText('Botox')).toBeInTheDocument();
    // owner has services.write → the create form is visible
    expect(screen.getByRole('heading', { name: 'Nuevo servicio' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear servicio' })).toBeInTheDocument();
  });

  it('switches the form to edit mode when a service row is edited', async () => {
    setup();
    await screen.findByText('Limpieza facial');

    await userEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);

    expect(
      await screen.findByRole('heading', { name: 'Editar servicio' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Actualizar servicio' })).toBeInTheDocument();
  });

  it('reorders a service through the reorder control', async () => {
    coreApi.reorderServices.mockResolvedValue({});
    setup();
    await screen.findByText('Limpieza facial');

    // the first row's "down" arrow moves Limpieza facial below Botox
    await userEvent.click(screen.getAllByRole('button', { name: 'Bajar orden' })[0]);

    expect(coreApi.reorderServices).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      [
        { id: 's-2', sort_order: 0 },
        { id: 's-1', sort_order: 1 },
      ],
    );
  });

  it('hides the write form but keeps the table for a read-only role', async () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    // agent has services.read but not services.write
    expect(await screen.findByText('Limpieza facial')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Nuevo servicio' })).toBeNull();
  });

  it('renders AccessDenied when the active tenant role lacks services.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Servicios', level: 1 })).toBeNull();
  });
});
