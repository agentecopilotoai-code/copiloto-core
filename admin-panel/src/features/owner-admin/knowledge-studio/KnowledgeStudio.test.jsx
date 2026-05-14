import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listKnowledgeDocuments: vi.fn(),
  createKnowledgeDocument: vi.fn(),
  updateKnowledgeDocument: vi.fn(),
  deleteKnowledgeDocument: vi.fn(),
  indexKnowledgeDocument: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
  evaluateIntent: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { KnowledgeStudio } from './KnowledgeStudio.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Knowledge Studio', summary: 'Base de conocimiento' };

const DOCUMENTS = [
  {
    id: 'doc-1',
    title: 'Política de cancelación',
    document_type: 'faq',
    source_type: 'manual',
    status: 'active',
    content: 'Puedes cancelar hasta 2 horas antes.',
    updated_at: '2026-05-10T12:00:00Z',
    metadata: { embedding_provider: 'openai' },
  },
  {
    id: 'doc-2',
    title: 'Catálogo 2026',
    document_type: 'reference',
    source_type: 'upload',
    status: 'draft',
    source_uri: 's3://kb/catalogo.pdf',
    updated_at: '2026-05-01T12:00:00Z',
    metadata: {},
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <KnowledgeStudio module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listKnowledgeDocuments.mockResolvedValue(DOCUMENTS);
});

describe('KnowledgeStudio', () => {
  it('renders the documents table with both documents', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Knowledge Studio', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Política de cancelación')).toBeInTheDocument();
    expect(screen.getByText('Catálogo 2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Subir documento' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test RAG' })).toBeInTheDocument();
  });

  it('opens the upload drawer from the header CTA', async () => {
    setup();
    await screen.findByText('Política de cancelación');

    await userEvent.click(screen.getByRole('button', { name: 'Subir documento' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Subir documento');
    expect(screen.getByRole('button', { name: 'Guardar archivo' })).toBeInTheDocument();
  });

  it('opens the create document drawer from the toolbar', async () => {
    setup();
    await screen.findByText('Política de cancelación');

    await userEvent.click(screen.getByRole('button', { name: 'Nuevo documento' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nuevo documento');
    expect(screen.getByRole('button', { name: 'Crear documento' })).toBeInTheDocument();
  });

  it('opens the RAG smoke-test drawer and evaluates a question', async () => {
    coreApi.evaluateIntent.mockResolvedValue({
      intent: 'pricing',
      confidence: 0.9,
      resolved_by: 'rag',
      status: 'answered',
      sufficient_context: true,
      answer: 'El precio es 380.000',
      chunks: [],
    });
    setup();
    await screen.findByText('Política de cancelación');

    await userEvent.click(screen.getByRole('button', { name: 'Test RAG' }));
    await userEvent.type(
      screen.getByPlaceholderText(/Cuánto dura la garantía/),
      '¿Cuánto cuesta el botox?',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Clasificar' }));

    expect(await screen.findByText('El precio es 380.000')).toBeInTheDocument();
    expect(coreApi.evaluateIntent.mock.calls[0][2].question).toBe('¿Cuánto cuesta el botox?');
  });

  it('renders AccessDenied when the active tenant role lacks knowledge.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Knowledge Studio', level: 1 })).toBeNull();
  });
});
