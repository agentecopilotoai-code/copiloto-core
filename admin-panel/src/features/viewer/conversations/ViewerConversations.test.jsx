import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Aislamos `coreApi` para no arrastrar todo el grafo del módulo. El feature
// reusa `useInboxData` verbatim, así que mockeamos todos los exports que ese
// hook importa. `openConversationStream` devuelve un fake socket con `close()`
// para que el efecto del stream sea inerte.
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
import { ViewerConversations } from './ViewerConversations.jsx';

const VIEWER_PROFILE = { sub: 'u-viewer' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Conversaciones', summary: 'Lectura' };

const CONVERSATIONS = [
  {
    id: 'conv-1',
    contact_label: 'María Pérez',
    contact_id: 'contact-1',
    status: 'human_required',
    latest_message_text: 'Hola, necesito ayuda',
    updated_at: '2026-05-14T09:00:00Z',
  },
  {
    id: 'conv-2',
    contact_label: 'Andrés Gómez',
    contact_id: 'contact-2',
    status: 'open',
    latest_message_text: 'Quiero agendar',
    updated_at: '2026-05-14T10:00:00Z',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <ViewerConversations module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: VIEWER_PROFILE };
  coreApi.listConversations.mockResolvedValue(CONVERSATIONS);
  coreApi.listComplaintConversations.mockResolvedValue([]);
  coreApi.getConversation.mockResolvedValue({});
});

describe('ViewerConversations', () => {
  it('renderiza el listado de conversaciones para un viewer con conversations.view', async () => {
    setup();

    // El PageHeader del feature, el chip de resumen, las tabs `Todas`/`Quejas`.
    expect(
      await screen.findByRole('heading', { name: 'Conversaciones', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Todas \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Quejas \(0\)/ })).toBeInTheDocument();

    // Una vez resuelve `listConversations`, los items se pintan vía
    // `ConversationListItem` — verificamos que ambos contactos aparezcan.
    await waitFor(() => {
      expect(screen.getByText('María Pérez')).toBeInTheDocument();
    });
    expect(screen.getByText('Andrés Gómez')).toBeInTheDocument();
    expect(coreApi.listConversations).toHaveBeenCalledWith(SESSION, 'tenant-acme');
  });

  it('cambia al filtro de quejas cuando se hace click en la tab', async () => {
    setup();
    await screen.findByText('María Pérez');

    await userEvent.click(screen.getByRole('tab', { name: /Quejas/ }));

    expect(screen.getByText('No hay quejas activas en este tenant.')).toBeInTheDocument();
  });

  it('NO renderiza ningún botón de write (criterio UI-010)', async () => {
    setup();
    await screen.findByText('María Pérez');

    // El formulario «Iniciar conversación» NO se renderiza (showStartForm=false).
    // El composer (`MessageComposer`) y las CTAs de handoff (`Tomar`, `Liberar`,
    // `Aceptar handoff`) tampoco — el orquestador no monta `ConversationView`.
    // Los Viewers ven sólo la lista + las tabs de filtro (que son read-only por
    // diseño: alternan qué subconjunto se pinta sin mutar nada en el servidor).
    expect(
      screen.queryByRole('button', { name: /iniciar conversación/i }),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: /enviar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /tomar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /liberar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /aceptar handoff/i })).toBeNull();

    // Las tabs SÍ existen (no son write) — sanity check para que el regex no
    // sea tan amplio como para matchearlas.
    expect(screen.getByRole('tab', { name: /Todas/ })).toBeInTheDocument();
  });

  it('renderiza AccessDenied cuando el rol del tenant carece de conversations.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    // `RequirePermission` corta el árbol antes del orquestador y muestra el
    // mensaje «Acceso restringido». El listado y el heading no se montan.
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Conversaciones', level: 1 }),
    ).toBeNull();
    // El composer / handoff CTAs / start-form tampoco se montan en este caso.
    expect(
      screen.queryByRole('button', { name: /iniciar conversación/i }),
    ).toBeNull();
  });
});
