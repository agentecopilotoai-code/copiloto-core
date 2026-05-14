import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getPlatformIncidents: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { getPlatformIncidents } from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Incidents } from './Incidents.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const INCIDENTS_RESPONSE = {
  generated_at: '2026-05-14T12:00:00Z',
  incidents: [
    {
      id: 'inc-1',
      kind: 'backup_failure',
      severity: 'P1',
      runbook: null,
      status: 'failed',
      is_open: true,
      tenant_id: null,
      tenant_name: null,
      tenant_slug: null,
      payload: { sha_mismatch: true },
      attempts: 3,
      last_error: 'SHA mismatch',
      scheduled_for: '2026-05-14T03:00:00Z',
      created_at: '2026-05-14T03:00:00Z',
      sent_at: null,
      updated_at: '2026-05-14T03:05:00Z',
    },
    {
      id: 'inc-2',
      kind: 'outbound_dlq_threshold',
      severity: 'P2',
      runbook: 'rate-limit-meta-hit.md',
      status: 'sent',
      is_open: false,
      tenant_id: 't-motos',
      tenant_name: 'Taller Motos BA',
      tenant_slug: 'taller-motos-ba',
      payload: { error_rate: 0.064 },
      attempts: 1,
      last_error: null,
      scheduled_for: '2026-05-14T11:00:00Z',
      created_at: '2026-05-14T11:00:00Z',
      sent_at: '2026-05-14T11:01:00Z',
      updated_at: '2026-05-14T11:01:00Z',
    },
  ],
  summary: {
    total: 2,
    open: 1,
    resolved: 1,
    by_severity: { P1: 1, P2: 1 },
    by_status: { failed: 1, sent: 1 },
    affected_tenants: 1,
  },
  note: 'Feed de incidentes derivado de app.operator_alerts.',
};

function setup() {
  return render(
    <MemoryRouter>
      <Incidents />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
  getPlatformIncidents.mockResolvedValue(INCIDENTS_RESPONSE);
});

describe('Incidents', () => {
  it('renders the header, KPIs and the incident rows', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Incidentes' }),
    ).toBeInTheDocument();

    const openKpi = screen.getByText('Incidentes abiertos').closest('article');
    expect(openKpi.textContent).toContain('1');

    expect(screen.getByText('Fallo de backup', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('Umbral DLQ outbound', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByText('Taller Motos BA')).toBeInTheDocument();
  });

  it('passes the status filter to the endpoint', async () => {
    setup();
    await screen.findByText('Fallo de backup', { selector: 'td' });

    getPlatformIncidents.mockClear();
    await userEvent.selectOptions(screen.getByLabelText('Estado'), 'failed');

    await waitFor(() => {
      expect(getPlatformIncidents).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ status: 'failed', limit: 200 }),
      );
    });
  });

  it('opens the drawer with payload and delivery timeline on row click', async () => {
    setup();
    await screen.findByText('Fallo de backup', { selector: 'td' });

    await userEvent.click(screen.getByText('Fallo de backup', { selector: 'td' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Timeline de entrega');
    expect(dialog.textContent).toContain('SHA mismatch');
    expect(dialog.textContent).toContain('sha_mismatch');
  });

  it('renders an error state and supports retry', async () => {
    getPlatformIncidents.mockRejectedValueOnce(new Error('incidents endpoint down'));
    setup();

    expect(
      await screen.findByText('incidents endpoint down'),
    ).toBeInTheDocument();

    getPlatformIncidents.mockResolvedValueOnce(INCIDENTS_RESPONSE);
    await userEvent.click(screen.getAllByRole('button', { name: 'Reintentar' })[0]);
    await screen.findByText('Fallo de backup', { selector: 'td' });
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Incidentes' })).toBeNull();
  });
});
