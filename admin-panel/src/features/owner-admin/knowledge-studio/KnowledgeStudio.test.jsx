import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  getKnowledgeStorageSettings: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
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
    metadata: { embedding_provider: 'openai', chunk_count: 12 },
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
  {
    id: 'doc-3',
    title: 'Promo del mes',
    document_type: 'faq',
    source_type: 'manual',
    status: 'indexing',
    updated_at: '2026-05-14T12:00:00Z',
    metadata: {},
  },
  {
    id: 'doc-4',
    title: 'Manual descontinuado',
    document_type: 'reference',
    source_type: 'upload',
    status: 'failed',
    source_uri: 's3://kb/old.pdf',
    updated_at: '2026-05-12T12:00:00Z',
    metadata: { extraction_error: 'pdf-parse: invalid header' },
  },
];

const STORAGE = {
  backend: 's3',
  // codex P2 (UI-016.2): `public_knowledge_storage_config` in app/api/v1/routes.py
  // sets `effective_bucket` to just the bucket name (or the global default
  // fallback). The `prefix` lives in a separate field and the UI must combine
  // them. Earlier mocks pre-combined the path which masked the bucket+prefix
  // bug — keep the mock honest to the real backend response shape.
  bucket: 'copilotoia-kb-prod',
  prefix: 'clinica-est-norte/',
  effective_bucket: 'copilotoia-kb-prod',
  secret_configured: true,
  total_bytes: 18.4 * 1024 * 1024,
  document_count: 4,
};

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <KnowledgeStudio module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listKnowledgeDocuments.mockResolvedValue(DOCUMENTS);
  coreApi.getKnowledgeStorageSettings.mockResolvedValue(STORAGE);
});

describe('KnowledgeStudio', () => {
  it('renders the documents table with all rows and the header CTAs', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Knowledge Studio', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Política de cancelación')).toBeInTheDocument();
    expect(screen.getByText('Catálogo 2026')).toBeInTheDocument();
    expect(screen.getByText('Promo del mes')).toBeInTheDocument();
    expect(screen.getByText('Manual descontinuado')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Subir documento' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test RAG' })).toBeInTheDocument();
  });

  it('renders the canonical column headers Documento / Tipo / Chunks / Origen / Estado / Actualizado', async () => {
    setup();
    await screen.findByText('Política de cancelación');

    expect(screen.getByRole('columnheader', { name: 'Documento' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Tipo' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Chunks' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Origen' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Estado' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Actualizado' })).toBeInTheDocument();
  });

  it('exposes filter tabs and queries the API per status when clicked', async () => {
    setup();
    await screen.findByText('Política de cancelación');

    const todos = screen.getByRole('tab', { name: /Todos/ });
    const fallidos = screen.getByRole('tab', { name: /Fallidos/ });

    // codex P2 (UI-016.2): with the status filter pushed to the API, only the
    // ACTIVE tab carries an accurate badge — inactive tabs can't be counted
    // from the currently loaded list (it only contains rows for one status).
    expect(within(todos).getByText('4')).toBeInTheDocument();

    // Switching to "Fallidos" refetches with `status=failed` so older failed
    // documents are not hidden by the API's `limit 250`. The mock list is
    // returned again (`listKnowledgeDocuments.mockResolvedValue`) — that's
    // expected for vitest; we assert the call carried the status param.
    await userEvent.click(fallidos);
    await waitFor(() => {
      const callArgs = coreApi.listKnowledgeDocuments.mock.calls.at(-1);
      expect(callArgs?.[2]).toMatchObject({ status: 'failed' });
    });
  });

  it('renders the Storage summary card with the effective bucket and size', async () => {
    setup();
    await screen.findByText('Política de cancelación');

    const storage = await screen.findByRole('heading', { name: 'Storage' });
    expect(storage).toBeInTheDocument();
    expect(screen.getAllByText('S3 dedicado').length).toBeGreaterThan(0);
    // `effective_bucket` is just the bucket; the prefix is appended by the UI.
    expect(
      screen.getByText('copilotoia-kb-prod/clinica-est-norte/'),
    ).toBeInTheDocument();
    expect(screen.getByText(/18\.4 MB/)).toBeInTheDocument();
  });

  it('still renders the documents table when storage fails to load', async () => {
    coreApi.getKnowledgeStorageSettings.mockRejectedValue(
      new Error('Sin permisos para leer storage.'),
    );
    setup();
    await screen.findByText('Política de cancelación');
    expect(
      await screen.findByText('Sin permisos para leer storage.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Storage' })).toBeInTheDocument();
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
