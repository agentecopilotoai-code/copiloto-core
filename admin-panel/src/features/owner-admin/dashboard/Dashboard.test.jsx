import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getAnalyticsOverview: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { getAnalyticsOverview } from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { Dashboard } from './Dashboard.jsx';

const OWNER_PROFILE = { sub: 'u-owner', name: 'Camila' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };

const CURRENT_OVERVIEW = {
  appointments: { created: 20, confirmed: 14, completed: 12, no_shows: 1, no_show_rate_pct: 7.4 },
  conversations: { open: 5, handoff: 2 },
  messages: { inbound: 320, outbound: 410 },
  revenue: { estimated_amount: 1840000 },
  feedback: { average_rating: 4.6, ratings_count: 18 },
};
const PREVIOUS_OVERVIEW = {
  appointments: { confirmed: 10, no_show_rate_pct: 9.0 },
  conversations: { open: 8, handoff: 1 },
  messages: { inbound: 280, outbound: 360 },
  revenue: { estimated_amount: 1500000 },
  feedback: { average_rating: 4.4, ratings_count: 15 },
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <Dashboard session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  // current window resolves first, previous second.
  getAnalyticsOverview
    .mockResolvedValueOnce(CURRENT_OVERVIEW)
    .mockResolvedValueOnce(PREVIOUS_OVERVIEW);
});

describe('Dashboard', () => {
  it('renders the greeting, KPIs and the derived alert', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: /Camila/ }),
    ).toBeInTheDocument();

    // KPI cards from analytics_overview.
    const confirmedKpi = screen.getByText('Citas confirmadas (7d)').closest('article');
    expect(confirmedKpi.textContent).toContain('14');

    // The handoff alert is derived from conversations.handoff = 2.
    expect(screen.getByText('2 conversaciones requieren handoff')).toBeInTheDocument();
  });

  it('navigates to a tenant-scoped module from a quick link', async () => {
    setup();
    await screen.findByRole('heading', { name: /Camila/ });
    // The quick-link buttons only mount once `getAnalyticsOverview` has
    // resolved (loading && !current shows the EmptyState instead). Use
    // findByRole so the click waits for the loaded state on slow runners.
    const contactosButton = await screen.findByRole('button', { name: /Contactos/ });

    await userEvent.click(contactosButton);
    expect(mockNavigate).toHaveBeenCalledWith('/t/acme/contacts');
  });

  it('renders an error state when the overview fetch fails', async () => {
    // Drop the beforeEach `*Once` queue so every call rejects.
    getAnalyticsOverview.mockReset();
    getAnalyticsOverview.mockRejectedValue(new Error('overview endpoint down'));
    setup();

    expect(await screen.findByText('No se pudo cargar el dashboard')).toBeInTheDocument();
    expect(screen.getByText('overview endpoint down')).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks analytics access', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Camila/ })).toBeNull();
  });
});
