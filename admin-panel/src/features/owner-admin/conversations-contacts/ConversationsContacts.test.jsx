import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listContacts: vi.fn(),
  listContactTags: vi.fn(),
  listTreatmentPackages: vi.fn(),
  getContactProfile: vi.fn(),
  listContactPackages: vi.fn(),
  listContactConsent: vi.fn(),
  assignContactTags: vi.fn(),
  unassignContactTag: vi.fn(),
  assignContactPackage: vi.fn(),
  refundContactPackage: vi.fn(),
  updateContactPhone: vi.fn(),
  createContactNote: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { ConversationsContacts } from './ConversationsContacts.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Contactos', summary: 'CRM' };

const CONTACTS = [
  { id: 'c-1', display_name: 'Laura Martínez', phone_e164: '+573001112233' },
  { id: 'c-2', display_name: 'Andrés Gómez', phone_e164: '+573004445566' },
];

const PROFILE_C1 = {
  contact: { id: 'c-1', display_name: 'Laura Martínez', phone_e164: '+573001112233' },
  tags: [],
  stats: { total_appointments: 8, completed_appointments: 6 },
  appointments: [],
  conversations: [],
  notes: [],
  referrals: {},
  qualification_questions: [],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <ConversationsContacts module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listContacts.mockResolvedValue(CONTACTS);
  coreApi.listContactTags.mockResolvedValue([{ id: 't-1', name: 'VIP' }]);
  coreApi.listTreatmentPackages.mockResolvedValue([]);
  coreApi.getContactProfile.mockResolvedValue(PROFILE_C1);
  coreApi.listContactPackages.mockResolvedValue([]);
  coreApi.listContactConsent.mockResolvedValue({ contact: {}, items: [] });
});

describe('ConversationsContacts', () => {
  it('renders the contact list and auto-loads the first contact into the drawer', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Contactos' }),
    ).toBeInTheDocument();
    // both contacts in the list
    expect(await screen.findByText('Laura Martínez')).toBeInTheDocument();
    expect(screen.getByText('Andrés Gómez')).toBeInTheDocument();
    // the first contact's profile auto-loads into the drawer (summary card)
    expect(await screen.findByText('Resumen')).toBeInTheDocument();
  });

  it('loads a contact profile when its card is selected', async () => {
    setup();
    await screen.findByText('Andrés Gómez');

    coreApi.getContactProfile.mockClear();
    await userEvent.click(screen.getByText('Andrés Gómez'));

    expect(coreApi.getContactProfile).toHaveBeenCalledWith(SESSION, 'tenant-acme', 'c-2');
  });

  it('passes the search term to listContacts on submit', async () => {
    setup();
    await screen.findByText('Laura Martínez');

    coreApi.listContacts.mockClear();
    await userEvent.type(screen.getByLabelText('Buscar'), 'laura');
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }));

    expect(coreApi.listContacts).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      expect.objectContaining({ q: 'laura' }),
    );
  });

  it('renders AccessDenied when the active tenant role lacks contacts.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Contactos' })).toBeNull();
  });
});
