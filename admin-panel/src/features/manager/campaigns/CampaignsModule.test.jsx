import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listCampaigns: vi.fn(),
  createCampaign: vi.fn(),
  updateCampaign: vi.fn(),
  previewCampaign: vi.fn(),
  launchCampaign: vi.fn(),
  cancelCampaign: vi.fn(),
  listContactSegments: vi.fn(),
  listContactTags: vi.fn(),
  listWhatsappTemplates: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { CampaignsModule } from './CampaignsModule.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['manager'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Campañas', summary: 'Marketing conversacional' };

const CAMPAIGNS = [
  {
    id: 'camp-1',
    name: 'Promo octubre clientes inactivos',
    status: 'draft',
    recipient_count: 120,
    sent_count: 0,
    scheduled_at: null,
  },
];
const TEMPLATES = [
  { id: 'tpl-1', name: 'campaign_promo_es', locale: 'es_CO', purpose: 'marketing' },
];
const SEGMENTS = [{ id: 'seg-1', name: 'Inactivos 90d', contact_count: 120 }];

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <CampaignsModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listCampaigns.mockResolvedValue(CAMPAIGNS);
  coreApi.listWhatsappTemplates.mockResolvedValue(TEMPLATES);
  coreApi.listContactSegments.mockResolvedValue(SEGMENTS);
  coreApi.listContactTags.mockResolvedValue([]);
});

describe('CampaignsModule', () => {
  it('renders the campaigns table for a manager', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Campañas', level: 1 }),
    ).toBeInTheDocument();
    // The campaign name appears in the table row and in the delivery panel header.
    expect(
      (await screen.findAllByText('Promo octubre clientes inactivos')).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Campañas (1)')).toBeInTheDocument();
    await waitFor(() => expect(coreApi.listCampaigns).toHaveBeenCalled());
  });

  it('opens the create campaign drawer from the header CTA', async () => {
    setup();
    await screen.findAllByText('Promo octubre clientes inactivos');

    await userEvent.click(screen.getByRole('button', { name: 'Nueva campaña' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nueva campaña');
    expect(screen.getByRole('button', { name: 'Crear borrador' })).toBeInTheDocument();
  });

  it('renders the saved-segment picker in the drawer', async () => {
    setup();
    await screen.findAllByText('Promo octubre clientes inactivos');

    await userEvent.click(screen.getByRole('button', { name: 'Nueva campaña' }));

    await screen.findByRole('dialog');
    expect(screen.getByText('Segmento guardado')).toBeInTheDocument();
    expect(screen.getByText('Inactivos 90d (120)')).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks campaigns.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Campañas', level: 1 })).toBeNull();
  });
});
