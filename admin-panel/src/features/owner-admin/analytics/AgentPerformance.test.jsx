import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getAnalyticsAgents: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { AgentPerformance } from './AgentPerformance.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Rendimiento del equipo', summary: 'Equipo' };

const AGENTS = {
  top_performer_user_id: 'agent-diana',
  totals: {
    agents: 3,
    messages_sent: 5688,
    handoffs_resolved: 356,
    handoffs_accepted: 360,
    revenue_attributed: 31840,
    appointments_confirmed: 276,
  },
  items: [
    {
      user_id: 'agent-diana',
      display_name: 'Diana Pérez',
      email: 'diana@acme.co',
      messages_sent: 1640,
      handoffs_resolved: 192,
      handoffs_accepted: 192,
      appointments_confirmed: 152,
      revenue_attributed: 17120,
      avg_response_time_seconds: 42,
      feedback_avg_rating: 4.9,
      feedback_ratings_count: 30,
    },
    {
      user_id: 'agent-luis',
      display_name: 'Luis Rivas',
      email: 'luis@acme.co',
      messages_sent: 1552,
      handoffs_resolved: 164,
      handoffs_accepted: 168,
      appointments_confirmed: 124,
      revenue_attributed: 14720,
      avg_response_time_seconds: 51,
      feedback_avg_rating: 4.8,
      feedback_ratings_count: 24,
    },
    {
      user_id: 'agent-paola',
      display_name: 'Paola Núñez',
      email: 'paola@acme.co',
      messages_sent: 2496,
      handoffs_resolved: 0,
      handoffs_accepted: 0,
      appointments_confirmed: 0,
      revenue_attributed: 0,
      avg_response_time_seconds: 28,
      feedback_avg_rating: 4.7,
      feedback_ratings_count: 18,
    },
  ],
};

function setup({ tenant = ACME, ...rest } = {}) {
  return render(
    <MemoryRouter>
      <AgentPerformance module={MODULE} session={SESSION} tenant={tenant} {...rest} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.getAnalyticsAgents.mockResolvedValue(AGENTS);
});

describe('AgentPerformance (UI-016.3)', () => {
  it('renders the four KPI tiles from the HTML mockup', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Rendimiento del equipo', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Mensajes humanos · mes')).toBeInTheDocument();
    expect(screen.getByText('Handoffs cerrados')).toBeInTheDocument();
    expect(screen.getByText('Ingreso atribuido equipo')).toBeInTheDocument();
    expect(screen.getByText('1ª respuesta media')).toBeInTheDocument();
  });

  it('renders the per-agent table sorted by revenue_attributed by default', async () => {
    setup();

    expect(await screen.findByText('Rendimiento por agente')).toBeInTheDocument();
    const rows = await screen.findAllByRole('row');
    // [header, diana, luis, paola] — diana has the highest revenue.
    expect(rows.length).toBeGreaterThanOrEqual(4);
    const bodyRows = rows.slice(1);
    const firstAgent = within(bodyRows[0]).getByText('Diana Pérez');
    expect(firstAgent).toBeInTheDocument();
    const secondAgent = within(bodyRows[1]).getByText('Luis Rivas');
    expect(secondAgent).toBeInTheDocument();
  });

  it('renders the "Distribución de carga" chart with a bar per agent', async () => {
    setup();

    expect(await screen.findByText('Distribución de carga')).toBeInTheDocument();
    const list = await screen.findByLabelText('Distribución de carga por agente');
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    // Sorted descending by messages_sent — Paola has the highest (2,496).
    expect(within(items[0]).getByText('Paola Núñez')).toBeInTheDocument();
  });

  it('exports a CSV when the "Exportar" button is clicked', async () => {
    // `URL.createObjectURL` is not provided by jsdom — stub it.
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    const createSpy = vi.fn(() => 'blob:rendimiento-equipo');
    const revokeSpy = vi.fn();
    URL.createObjectURL = createSpy;
    URL.revokeObjectURL = revokeSpy;
    try {
      setup();
      // Wait for the data to load (KPI strip + table + load distribution all
      // mention agents, but the export button is only enabled after data).
      await screen.findByText('Rendimiento por agente');

      await userEvent.click(screen.getByRole('button', { name: 'Exportar' }));

      expect(createSpy).toHaveBeenCalledTimes(1);
      const [blob] = createSpy.mock.calls[0];
      expect(blob).toBeInstanceOf(Blob);
      expect(blob.type).toMatch(/text\/csv/);
    } finally {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });

  it('renders AccessDenied when the active tenant role lacks analytics.tenant.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Rendimiento del equipo', level: 1 }),
    ).toBeNull();
  });

  it('hides the range select when an external range is provided by the container', async () => {
    setup({ range: { fromDate: '2026-04-01', toDate: '2026-04-30' } });
    await screen.findByText('Rendimiento por agente');
    const rangeSelect = screen.getByLabelText('Rango de fechas');
    expect(rangeSelect).toBeDisabled();
    await waitFor(() => {
      expect(coreApi.getAnalyticsAgents).toHaveBeenCalledWith(
        SESSION,
        'tenant-acme',
        { fromDate: '2026-04-01', toDate: '2026-04-30' },
      );
    });
  });
});
