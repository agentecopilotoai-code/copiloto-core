import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listMediaAssets: vi.fn(),
  uploadMediaAsset: vi.fn(),
  updateMediaAsset: vi.fn(),
  deleteMediaAsset: vi.fn(),
  listPromotions: vi.fn(),
  createPromotion: vi.fn(),
  updatePromotion: vi.fn(),
  deletePromotion: vi.fn(),
  listServices: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { MediaLibraryModule } from './MediaLibraryModule.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Medios y promociones', summary: 'Biblioteca de medios' };

const ASSETS = [
  {
    id: 'asset-1',
    label: 'Lobby principal',
    kind: 'image',
    size_bytes: 1024 * 1024,
    tags: ['lobby'],
    description: 'Recepción',
  },
];
const PROMOS = [
  {
    id: 'promo-1',
    name: 'Día de la Madre 2026',
    is_active: true,
    discount_percent: 20,
    applies_to_service_ids: [],
  },
];
const SERVICES = [{ id: 'svc-1', name: 'Limpieza facial' }];

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <MediaLibraryModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listMediaAssets.mockResolvedValue(ASSETS);
  coreApi.listPromotions.mockResolvedValue(PROMOS);
  coreApi.listServices.mockResolvedValue(SERVICES);
});

describe('MediaLibraryModule', () => {
  it('renders the media grid and the promotions list', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Medios y promociones', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Lobby principal')).toBeInTheDocument();
    expect(screen.getByText('Día de la Madre 2026')).toBeInTheDocument();
    expect(screen.getByText('Biblioteca (1)')).toBeInTheDocument();
    expect(screen.getByText('Promociones (1)')).toBeInTheDocument();
  });

  it('opens the media uploader from the header CTA', async () => {
    setup();
    await screen.findByText('Lobby principal');

    await userEvent.click(screen.getByRole('button', { name: 'Subir medio' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Subir medio');
    expect(screen.getByRole('button', { name: 'Subir' })).toBeInTheDocument();
  });

  it('opens the promotion drawer from the header CTA', async () => {
    setup();
    await screen.findByText('Lobby principal');

    await userEvent.click(screen.getByRole('button', { name: 'Nueva promoción' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nueva promoción');
    expect(screen.getByRole('button', { name: 'Crear promoción' })).toBeInTheDocument();
  });

  it('filters the media grid by the search box', async () => {
    coreApi.listMediaAssets.mockResolvedValue([
      ...ASSETS,
      { id: 'asset-2', label: 'Catálogo PDF', kind: 'pdf', size_bytes: 4 * 1024 * 1024, tags: [] },
    ]);
    setup();
    await screen.findByText('Lobby principal');

    await userEvent.type(screen.getByLabelText('Buscar medios'), 'catálogo');

    expect(screen.getByText('Catálogo PDF')).toBeInTheDocument();
    expect(screen.queryByText('Lobby principal')).toBeNull();
  });

  it('renders AccessDenied when the active tenant role lacks media.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Medios y promociones', level: 1 }),
    ).toBeNull();
  });
});
