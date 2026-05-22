import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
// `useDashboardData` (reusado por `useSummaryData`) llama únicamente a
// `getAnalyticsOverview` con ventana actual + previa.
vi.mock('../../../services/coreApi.js', () => ({
  getAnalyticsOverview: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { ViewerSummary } from './ViewerSummary.jsx';

const VIEWER_PROFILE = { sub: 'u-viewer' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Resumen del negocio', summary: 'Lectura' };

const CURRENT_OVERVIEW = {
  appointments: { confirmed: 42, created: 60, completed: 38, no_shows: 3, no_show_rate_pct: 5 },
  conversations: { open: 12, handoff: 2 },
  messages: { inbound: 410, outbound: 380 },
  revenue: { estimated_amount: 26400 },
};
const PREVIOUS_OVERVIEW = {
  appointments: { confirmed: 35, created: 52, completed: 30, no_shows: 5, no_show_rate_pct: 9 },
  conversations: { open: 14, handoff: 4 },
  messages: { inbound: 380, outbound: 350 },
  revenue: { estimated_amount: 22100 },
};

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <ViewerSummary module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: VIEWER_PROFILE, activeTenant: ACME };
  // current + previous windows en ese orden (igual que `useDashboardData`).
  coreApi.getAnalyticsOverview
    .mockResolvedValueOnce(CURRENT_OVERVIEW)
    .mockResolvedValueOnce(PREVIOUS_OVERVIEW);
});

describe('ViewerSummary', () => {
  it('renders the PageHeader y las KPIs reusadas del dashboard para un viewer', async () => {
    setup();

    expect(
      screen.getByRole('heading', { name: 'Resumen del negocio', level: 1 }),
    ).toBeInTheDocument();
    // Chip de período con formato es-CO: "Últimos 7 días · <Mes> <año>".
    expect(screen.getByLabelText('Período')).toHaveTextContent(/Últimos 7 días/);

    // Las KPIs vienen de `buildKpis(current, previous)` del dashboard — al
    // resolver los dos overviews debe pintar la grid `aria-label="Indicadores
    // del negocio"` con las 5 tarjetas de KpiCardWithDelta.
    await waitFor(() =>
      expect(screen.getByLabelText('Indicadores del negocio')).toBeInTheDocument(),
    );
    expect(screen.getByText('Citas confirmadas (7d)')).toBeInTheDocument();
    expect(screen.getByText('Conversaciones abiertas')).toBeInTheDocument();
    expect(screen.getByText('Ingresos estimados (7d)')).toBeInTheDocument();

    expect(coreApi.getAnalyticsOverview).toHaveBeenCalledTimes(2);
  });

  it('NO renderiza CTAs de escritura / quick links / acciones de alerta del Owner Dashboard', async () => {
    setup();
    await waitFor(() =>
      expect(screen.getByLabelText('Indicadores del negocio')).toBeInTheDocument(),
    );

    // Criterio UI-010: 100% de las write actions ocultas. El Owner Dashboard
    // monta `<DashboardQuickLinks>` (sección "Accesos rápidos") y
    // `<DashboardAlerts>` (sección "Alertas" con botones de navegación) — esta
    // vista NO debe renderizar ni uno ni el otro.
    expect(screen.queryByText('Accesos rápidos')).toBeNull();
    expect(screen.queryByText('Alertas')).toBeNull();
    expect(screen.queryByRole('button', { name: /Actualizar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Operations Desk/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Abrir Operations Desk/i })).toBeNull();
  });

  it('muestra EmptyState defensivo cuando el tenant aún no tiene id (carga inicial)', () => {
    // Defensive UX: el viewer ya está dentro del shell (tiene rol) pero el
    // tenant resuelto por el router todavía no expone `id`. La vista debe
    // mostrar un EmptyState y NO disparar fetch contra `getAnalyticsOverview`.
    setup({ tenant: { slug: 'acme', roles: ['viewer'] } });
    expect(screen.getByText('Selecciona un tenant')).toBeInTheDocument();
    expect(screen.queryByLabelText('Indicadores del negocio')).toBeNull();
    expect(coreApi.getAnalyticsOverview).not.toHaveBeenCalled();
  });

  it('renders AccessDenied cuando el rol del tenant carece de analytics.tenant.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Resumen del negocio', level: 1 }),
    ).toBeNull();
  });
});
