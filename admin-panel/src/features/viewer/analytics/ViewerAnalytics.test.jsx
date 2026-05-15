import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
// `AnalyticsPanel` llama 7 endpoints en paralelo en su `loadAll`, y
// `AgentPerformance` (que se importa al mismo nivel del módulo aunque sólo se
// monte cuando `activeTab === 'agents'`) añade un 8º (`getAnalyticsAgents`).
// El mock cubre los 8.
vi.mock('../../../services/coreApi.js', () => ({
  getAnalyticsAppointments: vi.fn(),
  getAnalyticsCampaigns: vi.fn(),
  getAnalyticsContacts: vi.fn(),
  getAnalyticsConversations: vi.fn(),
  getAnalyticsFunnel: vi.fn(),
  getAnalyticsOverview: vi.fn(),
  getAnalyticsReferrals: vi.fn(),
  getAnalyticsAgents: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { ViewerAnalytics } from './ViewerAnalytics.jsx';

const VIEWER_PROFILE = { sub: 'u-viewer' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Analítica', summary: 'KPIs read-only del negocio' };

// El `AnalyticsPanel` renderiza un bloque de KPIs que asume varios sub-objetos
// poblados en la respuesta de `getAnalyticsOverview` (feedback, retention,
// messages, etc.). Se construyen para evitar errores de runtime al pintar el
// dashboard — los valores son inocuos.
const OVERVIEW = {
  appointments: { confirmed: 42, created: 60, completed: 38, no_shows: 3, no_show_rate_pct: 5 },
  conversations: { open: 12, handoff: 2 },
  messages: { inbound: 410, outbound: 380 },
  revenue: { estimated_amount: 26400 },
  feedback: { ratings_count: 8, average_rating: 4.6 },
  retention: { retention_rate_pct: 72, recurring_contacts: 18 },
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <ViewerAnalytics module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: VIEWER_PROFILE };
  coreApi.getAnalyticsOverview.mockResolvedValue(OVERVIEW);
  coreApi.getAnalyticsConversations.mockResolvedValue({ daily_evolution: [] });
  coreApi.getAnalyticsAppointments.mockResolvedValue({ daily_evolution: [] });
  coreApi.getAnalyticsContacts.mockResolvedValue({});
  coreApi.getAnalyticsFunnel.mockResolvedValue({ steps: [] });
  coreApi.getAnalyticsCampaigns.mockResolvedValue({ rows: [] });
  coreApi.getAnalyticsReferrals.mockResolvedValue({ rows: [] });
  coreApi.getAnalyticsAgents.mockResolvedValue({ rows: [] });
});

describe('ViewerAnalytics', () => {
  it('renderiza el AnalyticsPanel reusado (eyebrow, título y tabs) para un viewer con analytics.tenant.read', async () => {
    setup();

    // El heading del panel legacy es h2 «Analítica del negocio»; el eyebrow es
    // el label del módulo. Ambos confirman que el panel se montó dentro del
    // wrapper read-only.
    expect(
      screen.getByRole('heading', { name: 'Analítica del negocio', level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Analítica')).toBeInTheDocument();

    // Tabs del panel reusado.
    expect(screen.getByRole('button', { name: 'Resumen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Funnel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Campañas' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agentes' })).toBeInTheDocument();

    // `loadAll` debe haberse disparado contra los 7 endpoints del panel.
    await waitFor(() =>
      expect(coreApi.getAnalyticsOverview).toHaveBeenCalledWith(
        SESSION,
        'tenant-acme',
        expect.objectContaining({ fromDate: expect.any(String), toDate: expect.any(String) }),
      ),
    );
    expect(coreApi.getAnalyticsConversations).toHaveBeenCalled();
    expect(coreApi.getAnalyticsAppointments).toHaveBeenCalled();
    expect(coreApi.getAnalyticsContacts).toHaveBeenCalled();
    expect(coreApi.getAnalyticsFunnel).toHaveBeenCalled();
    expect(coreApi.getAnalyticsCampaigns).toHaveBeenCalled();
    expect(coreApi.getAnalyticsReferrals).toHaveBeenCalled();
  });

  it('NO renderiza ningún CTA de escritura / export / descarga (criterio UI-010)', async () => {
    setup();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Analítica del negocio', level: 2 })).toBeInTheDocument(),
    );

    // Criterio global UI-010: 100% de las write actions ocultas. El
    // `AnalyticsPanel` legacy ya es read-only por construcción — no tiene
    // botones de exportar / descargar / copiar. Estas aserciones documentan
    // ese contrato.
    expect(screen.queryByRole('button', { name: /Exportar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Export/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Descargar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Copiar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Guardar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Editar/i })).toBeNull();
  });

  it('renderiza AccessDenied cuando el rol del tenant carece de analytics.tenant.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    // El panel real NO se monta — su heading no debe aparecer.
    expect(
      screen.queryByRole('heading', { name: 'Analítica del negocio', level: 2 }),
    ).toBeNull();
    // Y por lo tanto no debe disparar fetch contra los endpoints de analítica.
    expect(coreApi.getAnalyticsOverview).not.toHaveBeenCalled();
  });
});
