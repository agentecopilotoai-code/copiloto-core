import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getWhatsAppChannelHealth: vi.fn(),
  upsertWhatsAppChannel: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  createWhatsappTemplate: vi.fn(),
  deleteWhatsappTemplate: vi.fn(),
  syncWhatsappTemplates: vi.fn(),
  getWebChannel: vi.fn(),
  upsertWebChannel: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { WhatsAppOnboarding } from './WhatsAppOnboarding.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'WhatsApp', summary: 'Canal WhatsApp' };

const HEALTH = {
  status: 'healthy',
  checks: {
    meta_access_token_configured: true,
    app_secret_configured: true,
    verify_token_configured: true,
    delivery_ready: true,
  },
  channel: {
    status: 'active',
    provider: 'whatsapp_cloud_api',
    business_id: '123',
    waba_id: '456',
    phone_number_id: '789',
    account_mode: 'live',
  },
};

const TEMPLATES = [
  {
    id: 'tpl-1',
    name: 'appointment_confirmation_es',
    locale: 'es',
    category: 'utility',
    purpose: 'appointment_confirmation',
    status: 'approved',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <WhatsAppOnboarding module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.getWhatsAppChannelHealth.mockResolvedValue(HEALTH);
  coreApi.listWhatsappTemplates.mockResolvedValue(TEMPLATES);
  coreApi.getWebChannel.mockResolvedValue(null);
});

describe('WhatsAppOnboarding', () => {
  it('renders the wizard, health panel and templates panel for the WhatsApp tab', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'WhatsApp', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Configuración del canal')).toBeInTheDocument();
    expect(screen.getByText('Checklist de onboarding')).toBeInTheDocument();
    expect(screen.getByText('Plantillas de mensajes')).toBeInTheDocument();
    expect(await screen.findByText('appointment_confirmation_es')).toBeInTheDocument();
    // Health snapshot surfaces the loaded channel.
    expect(await screen.findByText('Salud del canal')).toBeInTheDocument();
  });

  it('switches to the web widget tab', async () => {
    setup();
    await screen.findByText('Configuración del canal');

    await userEvent.click(screen.getByRole('tab', { name: 'Widget Web' }));

    // The WhatsApp setup card is no longer rendered once the web tab is active.
    expect(screen.queryByText('Configuración del canal')).toBeNull();
  });

  it('creates a template through the templates form', async () => {
    coreApi.createWhatsappTemplate.mockResolvedValue({ id: 'tpl-2' });
    setup();
    await screen.findByText('Plantillas de mensajes');

    await userEvent.type(
      screen.getByPlaceholderText('appointment_confirmation_es'),
      'post_appointment_feedback_es',
    );
    await userEvent.type(
      screen.getByPlaceholderText(/Hola \{\{1\}\}/),
      'Gracias por tu visita',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Registrar plantilla' }));

    await waitFor(() => expect(coreApi.createWhatsappTemplate).toHaveBeenCalled());
    expect(coreApi.createWhatsappTemplate.mock.calls[0][2].name).toBe(
      'post_appointment_feedback_es',
    );
  });

  it('renders AccessDenied when the active tenant role lacks whatsapp.read', () => {
    mockTenantContext = { session: SESSION, profile: { sub: 'u-x', activeTenant: ACME } };
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'WhatsApp', level: 1 })).toBeNull();
  });
});
