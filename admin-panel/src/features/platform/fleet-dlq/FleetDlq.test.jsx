import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getPlatformOutboundDlq: vi.fn(),
  retryPlatformOutboundDlq: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

let mockTenantContext;
const mockHandleTenantCreated = vi.fn();
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { getPlatformOutboundDlq, retryPlatformOutboundDlq } from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { FleetDlq } from './FleetDlq.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const DLQ_RESPONSE = {
  generated_at: '2026-05-14T12:00:00Z',
  window_minutes: 60,
  since: '2026-05-14T11:00:00Z',
  summary: { total: 25, affected_tenants: 3, top_error_code: '80007', top_error_count: 14 },
  by_tenant: [
    {
      tenant_id: 't1',
      slug: 'taller-motos-ba',
      display_name: 'Taller Motos BA',
      total: 17,
      top_error_code: '80007',
      top_error_count: 14,
    },
    {
      tenant_id: 't2',
      slug: 'dental-lima',
      display_name: 'Dental Lima',
      total: 6,
      top_error_code: '131026',
      top_error_count: 6,
    },
  ],
  by_error_code: [
    { error_code: '80007', count: 14, runbook: 'rate-limit-meta-hit.md' },
    { error_code: '131026', count: 6, runbook: null },
  ],
  note: 'Agregado cross-tenant de app.messages.',
};

function setup() {
  return render(
    <MemoryRouter>
      <FleetDlq />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
    handleTenantCreated: mockHandleTenantCreated,
  };
  getPlatformOutboundDlq.mockResolvedValue(DLQ_RESPONSE);
  retryPlatformOutboundDlq.mockResolvedValue({ matched: 17, requeued: 17, message_ids: [], capped: false });
});

describe('FleetDlq', () => {
  it('renders the header, KPIs and the per-tenant + per-error-code breakdowns', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Outbound DLQ · fleet' }),
    ).toBeInTheDocument();

    const totalKpi = screen.getByText('Fallos en la ventana').closest('article');
    expect(totalKpi.textContent).toContain('25');

    expect(screen.getByText('Taller Motos BA')).toBeInTheDocument();
    expect(screen.getByText('Dental Lima')).toBeInTheDocument();
    // error-code panel with its runbook
    expect(screen.getByText('rate-limit-meta-hit.md', { exact: false })).toBeInTheDocument();
  });

  it('passes the window filter to the endpoint', async () => {
    setup();
    await screen.findByText('Taller Motos BA');

    getPlatformOutboundDlq.mockClear();
    await userEvent.selectOptions(screen.getByLabelText('Ventana'), '1440');

    await waitFor(() => {
      expect(getPlatformOutboundDlq).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ windowMinutes: 1440 }),
      );
    });
  });

  it('bulk-retries a tenant DLQ through the confirmation modal', async () => {
    setup();
    await screen.findByText('Taller Motos BA');

    await userEvent.click(screen.getAllByRole('button', { name: 'Reintentar' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Taller Motos BA');

    await userEvent.click(screen.getByRole('button', { name: 'Confirmar reintento' }));

    await waitFor(() => {
      expect(retryPlatformOutboundDlq).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ tenant_id: 't1', window_minutes: 60 }),
      );
    });
    expect(await screen.findByText(/Se reencolaron/)).toBeInTheDocument();
  });

  it('renders an error state when the list call fails', async () => {
    getPlatformOutboundDlq.mockRejectedValueOnce(new Error('dlq endpoint down'));
    setup();

    expect(await screen.findByText('dlq endpoint down')).toBeInTheDocument();
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
      handleTenantCreated: mockHandleTenantCreated,
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Outbound DLQ · fleet' })).toBeNull();
  });
});
