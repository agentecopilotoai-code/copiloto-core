import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
// Every named export `useInboxData` + `inboxData.js` import is stubbed;
// `openConversationStream` returns a fake socket with `close()` so the live
// stream effect is inert.
vi.mock('../../../services/coreApi.js', () => ({
  acceptConversationHandoff: vi.fn(),
  conversationMessageMediaUrl: vi.fn(() => 'https://media/url'),
  createConversationHandoff: vi.fn(),
  getConversation: vi.fn(),
  listComplaintConversations: vi.fn(),
  listConversations: vi.fn(),
  openConversationStream: vi.fn(() => ({ close: vi.fn(), readyState: 0 })),
  releaseConversation: vi.fn(),
  sendConversationMessage: vi.fn(),
  startConversation: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { MyHandoffs } from './MyHandoffs.jsx';

const AGENT_PROFILE = { sub: 'user-me' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['agent'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Mis handoffs', summary: 'Cola de handoffs' };

const CONVERSATIONS = [
  {
    id: 'c1',
    status: 'human_active',
    contact_label: 'Camila Velasco',
    contact_id: 'ct1',
    active_handoff_id: 'h1',
    active_handoff_assigned_to: 'user-me',
    updated_at: '2026-05-14T09:00:00Z',
  },
  {
    id: 'c2',
    status: 'human_required',
    contact_label: 'Andrés Gómez',
    contact_id: 'ct2',
    active_handoff_id: 'h2',
    active_handoff_assigned_to: null,
    updated_at: '2026-05-14T09:30:00Z',
  },
  {
    id: 'c3',
    status: 'open',
    contact_label: 'Sin escalar',
    contact_id: 'ct3',
    active_handoff_id: null,
    active_handoff_assigned_to: null,
    updated_at: '2026-05-14T08:00:00Z',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <MyHandoffs module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: AGENT_PROFILE };
  coreApi.listConversations.mockResolvedValue(CONVERSATIONS);
  coreApi.listComplaintConversations.mockResolvedValue([]);
  coreApi.getConversation.mockImplementation((_session, _tenantId, conversationId) =>
    Promise.resolve(CONVERSATIONS.find((c) => c.id === conversationId) || CONVERSATIONS[0]),
  );
});

describe('MyHandoffs', () => {
  it('renders the handoff queue, excluding bot-only conversations', async () => {
    setup();

    expect(
      screen.getByRole('heading', { name: 'Mis handoffs', level: 1 }),
    ).toBeInTheDocument();

    // Both escalated conversations show in the queue; the plain bot
    // conversation does not.
    await screen.findByText('Andrés Gómez');
    const queue = screen.getByRole('region', { name: 'Cola de handoffs' });
    expect(within(queue).getByText('Camila Velasco')).toBeInTheDocument();
    expect(within(queue).getByText('Andrés Gómez')).toBeInTheDocument();
    expect(within(queue).queryByText('Sin escalar')).toBeNull();
  });

  it('switches to the "Mías" tab and shows only the current user handoffs', async () => {
    setup();
    await screen.findByText('Andrés Gómez');
    const queue = screen.getByRole('region', { name: 'Cola de handoffs' });

    await userEvent.click(screen.getByRole('tab', { name: /Mías/ }));

    expect(within(queue).getByText('Camila Velasco')).toBeInTheDocument();
    expect(within(queue).queryByText('Andrés Gómez')).toBeNull();
  });

  it('switches to the "Sin asignar" tab and shows only unassigned handoffs', async () => {
    setup();
    await screen.findByText('Andrés Gómez');
    const queue = screen.getByRole('region', { name: 'Cola de handoffs' });

    await userEvent.click(screen.getByRole('tab', { name: /Sin asignar/ }));

    expect(within(queue).getByText('Andrés Gómez')).toBeInTheDocument();
    expect(within(queue).queryByText('Camila Velasco')).toBeNull();
  });

  it('selects an unassigned handoff and accepts it via the inbox handoff action', async () => {
    setup();
    await screen.findByText('Andrés Gómez');

    await userEvent.click(screen.getByRole('button', { name: 'Tomar' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Tomar handoff' }));

    await waitFor(() =>
      expect(coreApi.acceptConversationHandoff).toHaveBeenCalledWith(
        SESSION,
        'tenant-acme',
        'c2',
      ),
    );
  });

  it('renders AccessDenied when the active tenant role lacks conversations.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });

    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Mis handoffs', level: 1 })).toBeNull();
  });
});
