import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getContactProfile: vi.fn(),
  listContactConsent: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { ContactProfile } from './ContactProfile.jsx';

const AGENT_PROFILE = { sub: 'u-agent' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['agent'] };
const SESSION = { accessToken: 'tok' };

const PROFILE = {
  contact: {
    id: 'c-1',
    display_name: 'Laura Martínez',
    phone_e164: '+573000008842',
    wa_id: 'wa-laura',
    language: 'es-CO',
    created_at: '2025-02-05T10:00:00Z',
    opt_in_status: 'opted_in',
  },
  tags: [{ id: 't-1', name: 'VIP', color: '#facc15' }],
  appointments: [
    {
      id: 'a-1',
      service_name: 'Limpieza facial',
      status: 'completed',
      resource_name: 'Dra. Pérez',
      starts_at: '2026-04-12T15:00:00Z',
    },
  ],
  conversations: [
    { id: 'cv-1', status: 'closed', message_count: 12, updated_at: '2026-04-12T14:42:00Z' },
  ],
  notes: [{ id: 'n-1', body: 'Alérgica a la lidocaína.' }],
  referrals: { referred_by: null, referred_contacts: [] },
  stats: {
    total_appointments: 8,
    completed_appointments: 6,
    average_rating: 5,
    ratings_count: 4,
  },
};
const CONSENT = { contact: { opt_in_status: 'opted_in' }, items: [] };

function renderAt({ tenant = ACME, contactId = 'c-1' } = {}) {
  // BUG-220: el componente ahora resuelve el tenant activo via context
  // (useActiveTenant). Sincronizamos `mockTenantContext.activeTenant`
  // con el `tenant` del test para que los override de rol (ej. `roles=[]`)
  // se propaguen al hook usePermissions.
  mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter initialEntries={[`/t/acme/contacts/${contactId}`]}>
      <Routes>
        <Route path="/t/:tenantSlug" element={<Outlet context={{ activeTenant: tenant }} />}>
          <Route path="contacts/:contactId" element={<ContactProfile />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: AGENT_PROFILE, activeTenant: ACME };
  coreApi.getContactProfile.mockResolvedValue(PROFILE);
  coreApi.listContactConsent.mockResolvedValue(CONSENT);
});

describe('ContactProfile', () => {
  it('renders the focused profile for a contact id from the deep-link param', async () => {
    renderAt();

    await waitFor(() =>
      expect(coreApi.getContactProfile).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'c-1'),
    );
    expect(coreApi.listContactConsent).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      'c-1',
      { limit: 100 },
    );
    expect(
      await screen.findByRole('heading', { name: 'Laura Martínez', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Citas totales')).toBeInTheDocument();
    expect(screen.getByText('Historial')).toBeInTheDocument();
    expect(screen.getByText('Limpieza facial')).toBeInTheDocument();
  });

  it('shows a not-found state when getContactProfile returns nothing', async () => {
    coreApi.getContactProfile.mockResolvedValue(null);
    renderAt();

    expect(await screen.findByText('Contacto no encontrado')).toBeInTheDocument();
    expect(screen.queryByText('Historial')).toBeNull();
  });

  it('shows an error state when getContactProfile rejects', async () => {
    coreApi.getContactProfile.mockRejectedValue(new Error('boom'));
    renderAt();

    expect(await screen.findByText('No se pudo cargar la ficha')).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks contacts.view', () => {
    renderAt({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });

    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Laura Martínez', level: 1 }),
    ).toBeNull();
  });
});
