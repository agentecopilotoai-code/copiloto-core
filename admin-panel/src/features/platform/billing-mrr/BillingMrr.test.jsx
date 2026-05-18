import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getPlatformBillingMrr: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { getPlatformBillingMrr } from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { BillingMrr } from './BillingMrr.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const BILLING = {
  generated_at: '2026-05-14T12:00:00Z',
  mrr_by_currency: [
    { currency: 'COP', mrr: 18200000, active_subscriptions: 47 },
    { currency: 'USD', mrr: 440, active_subscriptions: 3 },
  ],
  mrr_by_plan: [
    {
      plan_name: 'Pro',
      billing_period: 'monthly',
      currency: 'COP',
      active_subscriptions: 30,
      past_due_subscriptions: 1,
      mrr: 14400000,
    },
    {
      plan_name: 'Starter',
      billing_period: 'monthly',
      currency: 'COP',
      active_subscriptions: 17,
      past_due_subscriptions: 0,
      mrr: 3060000,
    },
  ],
  churn: {
    window_days: 30,
    active_subscriptions: 50,
    past_due_subscriptions: 3,
    cancelled: 1,
    churn_rate: 0.0196,
  },
  failed_payments: {
    count: 2,
    items: [
      {
        tenant_id: 't-quito',
        slug: 'estetica-quito',
        display_name: 'Estética Quito',
        payment_provider: 'stripe',
        currency: 'COP',
        failed_count: 1,
        amount_pending: 480000,
      },
      {
        tenant_id: 't-motos',
        slug: 'taller-motos-ba',
        display_name: 'Taller Motos BA',
        payment_provider: 'mercadopago',
        currency: 'COP',
        failed_count: 1,
        amount_pending: 480000,
      },
    ],
  },
  tenants: [
    {
      tenant_id: 't-norte',
      slug: 'clinica-norte',
      display_name: 'Clínica Estética Norte',
      country_code: 'CO',
      active_subscriptions: 12,
      past_due_subscriptions: 0,
      next_billing_at: '2026-05-21T00:00:00Z',
      mrr_by_currency: [{ currency: 'COP', mrr: 5760000 }],
      mrr_total: 5760000,
    },
    {
      tenant_id: 't-motos',
      slug: 'taller-motos-ba',
      display_name: 'Taller Motos BA',
      country_code: 'AR',
      active_subscriptions: 5,
      past_due_subscriptions: 1,
      next_billing_at: '2026-05-18T00:00:00Z',
      mrr_by_currency: [{ currency: 'USD', mrr: 240 }],
      mrr_total: 240,
    },
  ],
  by_country: [
    {
      country_code: 'CO',
      tenant_count: 14,
      active_subscriptions: 40,
      mrr_by_currency: [{ currency: 'COP', mrr: 5800000 }],
    },
  ],
  note: 'MRR mensual-normalizada agregada desde TASK-0075.',
};

function setup() {
  return render(
    <MemoryRouter>
      <BillingMrr />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
  getPlatformBillingMrr.mockResolvedValue(BILLING);
});

describe('BillingMrr', () => {
  it('renders the header, KPIs, tenants table and plan composition', async () => {
    setup();
    // BUG-021: await un elemento que solo existe en estado loaded (un
    // tenant del mock data), no el heading que aparece también en loading.
    // Esto garantiza que la data async ya hidró el componente antes de
    // las assertions sync siguientes.
    await screen.findByText('Clínica Estética Norte');

    const churnKpi = screen.getByText('Churn 30d').closest('article');
    expect(churnKpi.textContent).toContain('2.0%');

    const failedKpi = screen
      .getByText('Cobros fallidos', { selector: '.label' })
      .closest('article');
    expect(failedKpi.textContent).toContain('2');

    // Tenants table + plan composition table.
    expect(screen.getByText('Composición del MRR')).toBeInTheDocument();
    expect(screen.getByText('Pro')).toBeInTheDocument();
  });

  it('renders failed payments and the country breakdown', async () => {
    setup();
    // BUG-021 (flaky CI): `findByRole('heading', {name: 'Billing & MRR'})`
    // resolvía inmediato porque el heading se renderiza en BOTH estados —
    // loading ("Cargando snapshot…") y loaded (data poblada). El siguiente
    // `getByText` (sync) corría antes de que el mock async de
    // `getPlatformBillingMrr` resolviera y los datos llegaran al DOM —
    // failing intermittently en CI (lento) y consistently bajo carga.
    // Fix: await un texto que SOLO existe en el estado loaded (un nombre
    // de tenant del mock BILLING data). Eso garantiza que la data ya
    // hidrató el componente antes de las assertions sync.
    await screen.findByText('Estética Quito');

    expect(screen.getByText('Países · MRR por geografía')).toBeInTheDocument();
    const countryItem = screen.getByText('CO', { selector: '.listName' }).closest('li');
    expect(countryItem.textContent).toContain('14 tenants');
  });

  it('renders an error state and supports retry', async () => {
    getPlatformBillingMrr.mockRejectedValueOnce(new Error('billing endpoint down'));
    setup();

    expect(
      await screen.findByText('No se pudo cargar Billing & MRR'),
    ).toBeInTheDocument();
    expect(screen.getByText('billing endpoint down')).toBeInTheDocument();

    getPlatformBillingMrr.mockResolvedValueOnce(BILLING);
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await screen.findByText('Clínica Estética Norte');
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Billing & MRR' })).toBeNull();
  });
});
