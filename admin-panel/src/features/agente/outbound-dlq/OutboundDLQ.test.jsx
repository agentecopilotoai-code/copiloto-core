import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listOutboundDlq: vi.fn(),
  retryOutboundDlqMessage: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// UI-011 — useConfirm() replaces the native browser confirm at the retry call
// site. Stub it inline (auto-confirms) so the retry path runs without mounting
// the global <ConfirmProvider/> in the test tree.
vi.mock('../../../components/ui/index.js', async () => {
  const actual = await vi.importActual('../../../components/ui/index.js');
  return {
    ...actual,
    useConfirm: () => async () => true,
    useToast: () => ({
      push: () => '',
      dismiss: () => {},
      success: () => '',
      error: () => '',
      info: () => '',
      warning: () => '',
    }),
  };
});

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { OutboundDLQ } from './OutboundDLQ.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Outbound DLQ', summary: 'Cola de fallos' };

const DLQ = {
  items: [
    {
      id: 'msg-84210000',
      error_code: '190',
      error_message: 'OAuthException · access token caducado',
      failed_at: '2026-05-14T10:00:00Z',
      message_type: 'template',
      body_preview: 'appointment_reminder_v3',
      payload: { to: '+57300...' },
    },
  ],
  totals_by_error_code: [
    { error_code: '190', count: 1 },
    { error_code: '131047', count: 6 },
  ],
};

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <OutboundDLQ module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listOutboundDlq.mockResolvedValue(DLQ);
});

describe('OutboundDLQ', () => {
  it('renders the error-code chips and the failed-message table', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Outbound DLQ', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Errores agrupados')).toBeInTheDocument();
    expect(await screen.findByText('appointment_reminder_v3')).toBeInTheDocument();
    // The friendly error label shows in both the filter chip and the table row.
    expect(screen.getAllByText('Token de acceso caducado').length).toBeGreaterThan(0);
  });

  it('retries a failed message through the row action', async () => {
    coreApi.retryOutboundDlqMessage.mockResolvedValue({});
    setup();
    await screen.findByText('appointment_reminder_v3');

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

    await waitFor(() => expect(coreApi.retryOutboundDlqMessage).toHaveBeenCalled());
    expect(coreApi.retryOutboundDlqMessage.mock.calls[0][2]).toBe('msg-84210000');
  });

  it('opens the message detail modal from the "Ver" action', async () => {
    setup();
    await screen.findByText('appointment_reminder_v3');

    await userEvent.click(screen.getByRole('button', { name: 'Ver' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Detalle del mensaje');
    expect(dialog.textContent).toContain('OAuthException');
  });

  it('renders AccessDenied when the active tenant role lacks outbound_dlq.retry', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Outbound DLQ', level: 1 })).toBeNull();
  });

  it('renders the empty-tenant card when there is no tenant id', () => {
    setup({ tenant: { id: undefined, slug: 'x', roles: ['owner'] } });
    expect(screen.getByText(/Selecciona un tenant/i)).toBeInTheDocument();
  });

  it('renders an error AlertBanner when the listOutboundDlq call fails and dismisses', async () => {
    coreApi.listOutboundDlq.mockRejectedValueOnce(new Error('dlq-fail'));
    setup();

    expect(await screen.findByText('dlq-fail')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(screen.queryByText('dlq-fail')).toBeNull();
  });

  it('refresh button retriggers the listOutboundDlq fetch', async () => {
    setup();
    await screen.findByText('appointment_reminder_v3');
    expect(coreApi.listOutboundDlq).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole('button', { name: 'Refrescar' }));
    await waitFor(() => expect(coreApi.listOutboundDlq).toHaveBeenCalledTimes(2));
  });
});
