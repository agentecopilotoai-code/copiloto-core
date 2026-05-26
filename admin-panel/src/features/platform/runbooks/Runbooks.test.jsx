import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getPlatformRunbooks: vi.fn(),
  getPlatformRunbook: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { getPlatformRunbooks, getPlatformRunbook } from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { Runbooks } from './Runbooks.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const CATALOGUE = {
  runbooks: [
    {
      slug: 'auth-token-expired',
      filename: 'auth-token-expired.md',
      title: 'Runbook — Token de auth vencido',
      category: 'Operaciones',
      size_bytes: 2942,
    },
    {
      slug: 'postgres-down',
      filename: 'postgres-down.md',
      title: 'Runbook — Postgres caído',
      category: 'Infraestructura',
      size_bytes: 3035,
    },
  ],
  categories: ['Infraestructura', 'Operaciones'],
};

const DETAIL = {
  slug: 'auth-token-expired',
  filename: 'auth-token-expired.md',
  title: 'Runbook — Token de auth vencido',
  category: 'Operaciones',
  html: '<article class="legal-document"><h1>Runbook — Token de auth vencido</h1><p>Sintoma del token.</p></article>',
};

function setup() {
  return render(
    <MemoryRouter>
      <Runbooks />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
  getPlatformRunbooks.mockResolvedValue(CATALOGUE);
  getPlatformRunbook.mockResolvedValue(DETAIL);
});

describe('Runbooks', () => {
  it('renders the header and the runbook catalogue', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Runbooks' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Runbook — Token de auth vencido')).toBeInTheDocument();
    expect(screen.getByText('Runbook — Postgres caído')).toBeInTheDocument();
  });

  it('filters the catalogue by category client-side', async () => {
    setup();
    await screen.findByText('Runbook — Token de auth vencido');

    await userEvent.selectOptions(screen.getByLabelText('Categoría'), 'Infraestructura');

    expect(screen.queryByText('Runbook — Token de auth vencido')).toBeNull();
    expect(screen.getByText('Runbook — Postgres caído')).toBeInTheDocument();
  });

  it('filters the catalogue by search text client-side', async () => {
    setup();
    await screen.findByText('Runbook — Token de auth vencido');

    await userEvent.type(screen.getByLabelText('Buscar'), 'postgres');

    expect(screen.queryByText('Runbook — Token de auth vencido')).toBeNull();
    expect(screen.getByText('Runbook — Postgres caído')).toBeInTheDocument();
  });

  it('opens the viewer with the server-rendered HTML on card click', async () => {
    setup();
    await screen.findByText('Runbook — Token de auth vencido');

    await userEvent.click(screen.getByText('Runbook — Token de auth vencido'));

    const dialog = await screen.findByRole('dialog');
    expect(getPlatformRunbook).toHaveBeenCalledWith(expect.anything(), 'auth-token-expired');
    expect(dialog.textContent).toContain('Sintoma del token.');
  });

  it('error path: pinta EmptyState con Reintentar y dispara refresh', async () => {
    getPlatformRunbooks.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(CATALOGUE);
    setup();
    expect(await screen.findByText(/No se pudo cargar/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await screen.findByText('Runbook — Postgres caído');
  });

  it('Actualizar dispara refresh', async () => {
    setup();
    await screen.findByText('Runbook — Postgres caído');
    getPlatformRunbooks.mockClear();
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar' }));
    await waitFor(() => {
      expect(getPlatformRunbooks).toHaveBeenCalled();
    });
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Runbooks' })).toBeNull();
  });
});
