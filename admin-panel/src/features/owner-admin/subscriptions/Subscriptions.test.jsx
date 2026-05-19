import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listSubscriptionPlans: vi.fn(),
  listContactSubscriptions: vi.fn(),
  createSubscriptionPlan: vi.fn(),
  updateSubscriptionPlan: vi.fn(),
  archiveSubscriptionPlan: vi.fn(),
  cancelContactSubscription: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { Subscriptions } from './Subscriptions.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Suscripciones', summary: 'Cobros recurrentes' };

const PLANS = [
  {
    id: 'plan-vip',
    name: 'Membresía VIP mensual',
    billing_period: 'monthly',
    price_amount: 280000,
    currency: 'COP',
    status: 'active',
  },
  {
    id: 'plan-anual',
    name: 'Anual premium',
    billing_period: 'yearly',
    price_amount: 2400000,
    currency: 'COP',
    status: 'archived',
  },
];

const SUBSCRIBERS = [
  {
    id: 'sub-1',
    contact_display_name: 'Laura Martínez',
    plan_id: 'plan-vip',
    plan_name: 'Membresía VIP mensual',
    status: 'active',
    next_billing_at: '2026-05-21T00:00:00Z',
  },
  {
    id: 'sub-2',
    contact_display_name: 'Camila Velasco',
    plan_id: 'plan-vip',
    plan_name: 'Membresía VIP mensual',
    status: 'past_due',
    retry_payment_link: 'https://stripe.test/retry',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <Subscriptions module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listSubscriptionPlans.mockResolvedValue(PLANS);
  coreApi.listContactSubscriptions.mockResolvedValue(SUBSCRIBERS);
});

describe('Subscriptions', () => {
  it('renders the KPI grid, the plans panel and the subscribers table', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Suscripciones', level: 1 }),
    ).toBeInTheDocument();
    // "Anual premium" only appears in the plans panel (no subscriber uses it).
    expect(await screen.findByText('Anual premium')).toBeInTheDocument();
    // "Laura Martínez" only appears in the subscribers table.
    expect(screen.getByText('Laura Martínez')).toBeInTheDocument();
    // Past-due retry link surfaces in the subscribers table.
    expect(screen.getByRole('link', { name: 'Reintentar cobro' })).toBeInTheDocument();
  });

  it('opens the create modal from the page header CTA', async () => {
    setup();
    await screen.findByText('Anual premium');

    await userEvent.click(screen.getByRole('button', { name: 'Nuevo plan' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nuevo plan');
    expect(screen.getByRole('button', { name: 'Crear plan' })).toBeInTheDocument();
  });

  it('opens the edit modal pre-filled when a plan is edited', async () => {
    setup();
    await screen.findByText('Anual premium');

    await userEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Editar plan');
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeInTheDocument();
  });

  it('filters the subscribers table by the selected tab', async () => {
    setup();
    await screen.findByText('Laura Martínez');

    await userEvent.click(screen.getByRole('tab', { name: /Past-due/ }));

    expect(screen.getByText('Camila Velasco')).toBeInTheDocument();
    expect(screen.queryByText('Laura Martínez')).toBeNull();
  });

  it('renders AccessDenied when the active tenant role lacks subscriptions.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Suscripciones', level: 1 })).toBeNull();
  });
});
