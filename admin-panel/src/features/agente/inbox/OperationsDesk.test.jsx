import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
// Every named export the feature imports is stubbed; `openConversationStream`
// returns a fake socket with a `close` method so the stream effect is inert.
vi.mock('../../../services/coreApi.js', () => ({
  acceptConversationHandoff: vi.fn(),
  assignContactTags: vi.fn(),
  cancelAppointment: vi.fn(),
  conversationMessageMediaUrl: vi.fn(() => 'https://media/url'),
  createAppointment: vi.fn(),
  createContactNote: vi.fn(),
  createConversationHandoff: vi.fn(),
  createQuote: vi.fn(),
  createResource: vi.fn(),
  createServiceRequest: vi.fn(),
  generateAppointmentPaymentLink: vi.fn(),
  getConversation: vi.fn(),
  getQuoteForSr: vi.fn(),
  getTenantAvailability: vi.fn(),
  listAppointmentFeedback: vi.fn(),
  listAppointments: vi.fn(),
  listComplaintConversations: vi.fn(),
  listContactTags: vi.fn(),
  listConversations: vi.fn(),
  listMediaAssets: vi.fn(),
  listResources: vi.fn(),
  listServiceRequests: vi.fn(),
  openConversationStream: vi.fn(() => ({ close: vi.fn(), readyState: 0 })),
  patchQuote: vi.fn(),
  patchServiceRequest: vi.fn(),
  releaseConversation: vi.fn(),
  sendAppointmentPaymentLink: vi.fn(),
  sendConversationMessage: vi.fn(),
  sendQuote: vi.fn(),
  startConversation: vi.fn(),
  unassignContactTag: vi.fn(),
  updateAppointment: vi.fn(),
  updateAppointmentPaymentStatus: vi.fn(),
  updateResource: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { OperationsDesk } from './OperationsDesk.jsx';

const AGENT_PROFILE = { sub: 'u-agent' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['agent'], vertical_code: 'salon' };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Inbox operativo', summary: 'Conversaciones del tenant' };

const CONVERSATIONS = [
  {
    id: 'conv-1',
    contact_label: 'María Pérez',
    contact_id: 'contact-1',
    status: 'human_required',
    latest_message_text: 'Hola, necesito ayuda',
    updated_at: '2026-05-14T09:00:00Z',
  },
];
const CONVERSATION_DETAIL = {
  id: 'conv-1',
  contact_label: 'María Pérez',
  contact_id: 'contact-1',
  status: 'human_required',
  messages: [
    {
      id: 'msg-1',
      direction: 'inbound',
      message_type: 'text',
      body_text: 'Hola, necesito ayuda',
      sender_actor_type: 'contact',
      created_at: '2026-05-14T09:00:00Z',
      status: 'sent',
    },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <OperationsDesk module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: AGENT_PROFILE };
  coreApi.listConversations.mockResolvedValue(CONVERSATIONS);
  coreApi.listComplaintConversations.mockResolvedValue([]);
  coreApi.getConversation.mockResolvedValue(CONVERSATION_DETAIL);
  coreApi.listResources.mockResolvedValue([]);
  coreApi.listAppointments.mockResolvedValue([]);
  coreApi.listMediaAssets.mockResolvedValue([]);
  coreApi.listContactTags.mockResolvedValue([]);
  coreApi.getTenantAvailability.mockResolvedValue({ resources: [] });
  coreApi.listServiceRequests.mockResolvedValue([]);
});

describe('OperationsDesk (Operación · Inbox)', () => {
  it('renders the inbox list for an agent', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Inbox operativo', level: 2 }),
    ).toBeInTheDocument();
    // The contact name appears in the list item and (once auto-selected) the
    // conversation detail header.
    expect((await screen.findAllByText('María Pérez')).length).toBeGreaterThan(0);
    expect(screen.getByRole('tab', { name: /Todas \(1\)/ })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Iniciar conversación' }),
    ).toBeInTheDocument();
    await waitFor(() => expect(coreApi.listConversations).toHaveBeenCalled());
  });

  it('opens the WebSocket conversation stream on mount', async () => {
    setup();
    await screen.findAllByText('María Pérez');
    expect(coreApi.openConversationStream).toHaveBeenCalledWith(SESSION, 'tenant-acme');
  });

  it('shows the conversation detail when a conversation is selected', async () => {
    setup();

    await userEvent.click((await screen.findAllByText('María Pérez'))[0]);

    await waitFor(() => expect(coreApi.getConversation).toHaveBeenCalled());
    expect(await screen.findByText('Handoff humano')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tomar conversación' })).toBeInTheDocument();
    expect(screen.getByText('Etiquetas y notas')).toBeInTheDocument();
  });

  it('switches to the complaints filter tab', async () => {
    setup();
    await screen.findAllByText('María Pérez');

    await userEvent.click(screen.getByRole('tab', { name: /Quejas/ }));

    expect(screen.getByText('No hay quejas activas en este tenant.')).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks conversations.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Inbox operativo', level: 2 })).toBeNull();
  });

  // ─── UI-016.8-FU: mobile state machine list ↔ detail ────────────────────

  describe('UI-016.8-FU mobile state machine', () => {
    it('arranca con data-mobile-view="list" en el layout wrapper', async () => {
      const { container } = setup();
      await screen.findAllByText('María Pérez');
      const layout = container.querySelector('.operations-layout');
      expect(layout).not.toBeNull();
      // Default state: la lista es la vista activa hasta que el usuario
      // selecciona una conversación. En desktop el CSS ignora el atributo
      // (se ve side-by-side); en mobile, el CSS lo lee para mostrar solo
      // el panel correspondiente.
      expect(layout?.getAttribute('data-mobile-view')).toBe('list');
    });

    it('cambia a data-mobile-view="detail" al seleccionar una conversación', async () => {
      const { container } = setup();
      await userEvent.click((await screen.findAllByText('María Pérez'))[0]);
      await waitFor(() => expect(coreApi.getConversation).toHaveBeenCalled());
      const layout = container.querySelector('.operations-layout');
      expect(layout?.getAttribute('data-mobile-view')).toBe('detail');
    });

    it('renderiza el botón "Volver a la lista" en el detalle (visible solo en mobile vía CSS)', async () => {
      setup();
      await userEvent.click((await screen.findAllByText('María Pérez'))[0]);
      await waitFor(() => expect(coreApi.getConversation).toHaveBeenCalled());
      // El back button existe en el DOM siempre; el CSS lo oculta en
      // desktop (display: none) y lo muestra solo a < 480px. La presencia
      // del aria-label es suficiente para validar la accesibilidad.
      expect(
        screen.getByRole('button', { name: 'Volver a la lista de conversaciones' }),
      ).toBeInTheDocument();
    });

    it('back button restaura mobileView a "list" sin perder la selección', async () => {
      const { container } = setup();
      await userEvent.click((await screen.findAllByText('María Pérez'))[0]);
      await waitFor(() => expect(coreApi.getConversation).toHaveBeenCalled());
      const layout = container.querySelector('.operations-layout');
      expect(layout?.getAttribute('data-mobile-view')).toBe('detail');

      await userEvent.click(
        screen.getByRole('button', { name: 'Volver a la lista de conversaciones' }),
      );
      expect(layout?.getAttribute('data-mobile-view')).toBe('list');
      // selectedConversationId NO se limpia: el usuario puede reabrir el
      // mismo detalle sin perder contexto (volver al detalle sería
      // re-click sobre el item).
    });

    it('handoff "Tomar conversación" sigue funcionando desde el detalle mobile', async () => {
      // Regression gate: el state machine de UI-016.8-FU no debe romper
      // las acciones del detalle (handoff, release, mensaje). Cubre la
      // preocupación del ticket "el handoff Tomar sigue funcionando desde
      // el detalle mobile".
      coreApi.acceptConversationHandoff.mockResolvedValue({});
      const { container } = setup();
      await userEvent.click((await screen.findAllByText('María Pérez'))[0]);
      await waitFor(() => expect(coreApi.getConversation).toHaveBeenCalled());

      // Estamos en 'detail' → el botón Tomar existe y dispara la acción.
      const layout = container.querySelector('.operations-layout');
      expect(layout?.getAttribute('data-mobile-view')).toBe('detail');

      await userEvent.click(screen.getByRole('button', { name: 'Tomar conversación' }));
      await waitFor(() =>
        expect(coreApi.acceptConversationHandoff).toHaveBeenCalledWith(
          SESSION,
          'tenant-acme',
          'conv-1',
        ),
      );
    });

    it('cambia a data-mobile-view="detail" al iniciar una conversación nueva (codex P2 fix)', async () => {
      // Regression del codex P2 review en PR #206: handleStartConversation
      // setea selectedConversationId directamente (sin pasar por
      // selectConversation), por lo que sin setMobileView('detail') explícito,
      // en mobile el detalle recién creado quedaría oculto por el CSS y el
      // usuario se quedaría en la lista sin ver su conversación nueva.
      const NEW_CONVERSATION = {
        id: 'conv-new',
        contact_label: 'Juan Nuevo',
        contact_id: 'contact-new',
        status: 'open',
        messages: [],
      };
      coreApi.startConversation.mockResolvedValue(NEW_CONVERSATION);

      const { container } = setup();
      await screen.findAllByText('María Pérez');

      // Llenar el form mínimo (teléfono + mensaje inicial) y submit.
      await userEvent.type(
        screen.getByLabelText(/Teléfono.*WhatsApp/i),
        '+573001234567',
      );
      await userEvent.type(
        screen.getByLabelText(/Mensaje inicial/i),
        'Hola Juan',
      );
      await userEvent.click(screen.getByRole('button', { name: 'Iniciar conversación' }));

      await waitFor(() => expect(coreApi.startConversation).toHaveBeenCalled());

      const layout = container.querySelector('.operations-layout');
      expect(layout?.getAttribute('data-mobile-view')).toBe('detail');
    });
  });
});
