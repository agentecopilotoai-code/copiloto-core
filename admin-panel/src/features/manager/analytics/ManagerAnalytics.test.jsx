import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getAnalyticsOverview: vi.fn(),
  getAnalyticsFunnel: vi.fn(),
  getAnalyticsAgents: vi.fn(),
  getAnalyticsCampaigns: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { ManagerAnalytics } from './ManagerAnalytics.jsx';

const MANAGER_PROFILE = { sub: 'u-manager' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['manager'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Analítica', summary: 'Cómo va el negocio' };

const OVERVIEW = {
  revenue: { estimated_amount: 26400 },
  appointments: { completed: 312, confirmed: 340, no_show_rate_pct: 8 },
  retention: { retention_rate_pct: 41, recurring_contacts: 120 },
  conversations: { handoff: 5 },
};
const FUNNEL = {
  by_channel: [
    { channel: 'whatsapp', steps: [{ step: 'appointments_scheduled', count: 174 }] },
  ],
};
const AGENTS = {
  top_performer_user_id: 'agent-1',
  items: [
    {
      user_id: 'agent-1',
      display_name: 'Diana Pérez',
      email: 'diana@acme.co',
      messages_sent: 412,
      handoffs_resolved: 38,
      appointments_confirmed: 38,
      revenue_attributed: 4280,
      avg_response_time_seconds: 42,
      feedback_avg_rating: 4.9,
      feedback_ratings_count: 30,
    },
  ],
};
const CAMPAIGNS = {
  items: [
    {
      campaign_id: 'c1',
      name: 'Promo Día de la Madre',
      status: 'sent',
      recipients: 1240,
      appointments_attributed: 142,
      revenue_attributed: 12480,
    },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <ManagerAnalytics module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: MANAGER_PROFILE };
  coreApi.getAnalyticsOverview.mockResolvedValue(OVERVIEW);
  coreApi.getAnalyticsFunnel.mockResolvedValue(FUNNEL);
  coreApi.getAnalyticsAgents.mockResolvedValue(AGENTS);
  coreApi.getAnalyticsCampaigns.mockResolvedValue(CAMPAIGNS);
});

describe('ManagerAnalytics', () => {
  it('renders the page header and fetches every analytics endpoint', async () => {
    setup();

    expect(
      screen.getByRole('heading', { name: 'Analítica', level: 1 }),
    ).toBeInTheDocument();
    await waitFor(() => expect(coreApi.getAnalyticsOverview).toHaveBeenCalled());
    expect(coreApi.getAnalyticsFunnel).toHaveBeenCalled();
    expect(coreApi.getAnalyticsAgents).toHaveBeenCalled();
    expect(coreApi.getAnalyticsCampaigns).toHaveBeenCalled();
  });

  it('renders the KPIs, agent table and conversion funnel for a manager', async () => {
    setup();

    expect(await screen.findByText('Ingreso estimado')).toBeInTheDocument();
    expect(screen.getByText('Retención 90d')).toBeInTheDocument();
    expect(screen.getByText('Rendimiento por agente')).toBeInTheDocument();
    expect(screen.getByText('Diana Pérez')).toBeInTheDocument();
    expect(screen.getByText('Top')).toBeInTheDocument();
    expect(screen.getByLabelText('Conversión por canal')).toBeInTheDocument();
  });

  it('renders the recent campaigns summary', async () => {
    setup();

    expect(await screen.findByText('Promo Día de la Madre')).toBeInTheDocument();
    expect(screen.getByText('Enviada')).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks analytics.tenant.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Analítica', level: 1 }),
    ).toBeNull();
  });
});
