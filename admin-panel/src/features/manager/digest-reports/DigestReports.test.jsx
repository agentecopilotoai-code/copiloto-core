import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listDigestSubscriptions: vi.fn(),
  createDigestSubscription: vi.fn(),
  updateDigestSubscription: vi.fn(),
  deleteDigestSubscription: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { DigestReports } from './DigestReports.jsx';

const MANAGER_PROFILE = { sub: 'u-manager' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['manager'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Reportes · Digest', summary: 'Digest periódico' };

const SUBSCRIPTIONS = {
  subscriptions: [
    {
      id: 'sub-1',
      recipient_email: 'camila@acme.co',
      recipient_whatsapp: null,
      cadence: 'daily',
      enabled: true,
      last_sent_at: '2026-05-14T08:00:00Z',
    },
    {
      id: 'sub-2',
      recipient_email: 'diana@acme.co',
      recipient_whatsapp: '+573001234567',
      cadence: 'weekly',
      enabled: false,
      last_sent_at: null,
    },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <DigestReports module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: MANAGER_PROFILE };
  coreApi.listDigestSubscriptions.mockResolvedValue(SUBSCRIPTIONS);
});

describe('DigestReports', () => {
  it('renders the subscribers panel and table for a manager', async () => {
    setup();

    expect(
      screen.getByRole('heading', { name: 'Reportes · Digest', level: 1 }),
    ).toBeInTheDocument();
    await waitFor(() => expect(coreApi.listDigestSubscriptions).toHaveBeenCalled());
    expect(
      screen.getByText('Suscripciones a resúmenes (TASK-0067)'),
    ).toBeInTheDocument();
    expect(await screen.findByText('camila@acme.co')).toBeInTheDocument();
    expect(screen.getByText('diana@acme.co')).toBeInTheDocument();
  });

  it('renders the "Suscribir destinatario" create form', async () => {
    setup();

    await waitFor(() => expect(coreApi.listDigestSubscriptions).toHaveBeenCalled());
    expect(screen.getByText('Email del destinatario')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Suscribir destinatario' }),
    ).toBeInTheDocument();
  });

  it('validates that at least one email or whatsapp is provided', async () => {
    setup();

    await waitFor(() => expect(coreApi.listDigestSubscriptions).toHaveBeenCalled());
    await userEvent.click(
      screen.getByRole('button', { name: 'Suscribir destinatario' }),
    );
    expect(
      await screen.findByText('Indica al menos un email o un WhatsApp.'),
    ).toBeInTheDocument();
    expect(coreApi.createDigestSubscription).not.toHaveBeenCalled();
  });

  it('renders AccessDenied when the active tenant role lacks digest.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Reportes · Digest', level: 1 }),
    ).toBeNull();
  });
});
