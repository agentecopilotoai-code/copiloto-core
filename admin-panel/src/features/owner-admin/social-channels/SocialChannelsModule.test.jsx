import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listMessengerChannels: vi.fn(),
  upsertMessengerChannel: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { SocialChannelsModule } from './SocialChannelsModule.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Redes sociales', summary: 'Instagram + Messenger' };

const CHANNELS = {
  channels: [
    {
      provider: 'instagram_messenger',
      status: 'active',
      account_mode: 'live',
      instagram_account_id: 'IG-42',
      service_window_hours: 24,
      token_configured: true,
      app_secret_configured: true,
      verify_token_configured: true,
    },
  ],
};

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <SocialChannelsModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listMessengerChannels.mockResolvedValue(CHANNELS);
});

describe('SocialChannelsModule', () => {
  it('renders both provider tabs, the status panel and the form', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Redes sociales', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Instagram DM' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Facebook Messenger' })).toBeInTheDocument();
    // Instagram channel is configured → its recipient id shows in the status panel.
    expect(await screen.findByText('IG-42')).toBeInTheDocument();
    expect(screen.getByText('Configurar Instagram DM')).toBeInTheDocument();
  });

  it('switches to the Facebook Messenger provider tab', async () => {
    setup();
    await screen.findByText('Configurar Instagram DM');

    await userEvent.click(screen.getByRole('tab', { name: 'Facebook Messenger' }));

    expect(screen.getByText('Configurar Facebook Messenger')).toBeInTheDocument();
    // Messenger has no channel configured → empty state.
    expect(screen.getByText('Sin configurar')).toBeInTheDocument();
  });

  it('submits the upsert form for the active provider', async () => {
    coreApi.upsertMessengerChannel.mockResolvedValue({
      provider: 'instagram_messenger',
      status: 'active',
    });
    setup();
    await screen.findByText('Configurar Instagram DM');

    await userEvent.type(
      screen.getByLabelText('Instagram Business Account ID', { exact: false }),
      'IG-99',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Guardar canal' }));

    await waitFor(() => expect(coreApi.upsertMessengerChannel).toHaveBeenCalled());
    const payload = coreApi.upsertMessengerChannel.mock.calls[0][2];
    expect(payload.provider).toBe('instagram_messenger');
    expect(payload.recipient_account_id).toBe('IG-99');
  });

  it('renders AccessDenied when the active tenant role lacks social_channels.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Redes sociales', level: 1 })).toBeNull();
  });
});
