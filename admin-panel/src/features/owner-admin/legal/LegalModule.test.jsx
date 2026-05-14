import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listLegalDocuments: vi.fn(),
  createLegalDocumentDraft: vi.fn(),
  publishLegalDocument: vi.fn(),
  legalDocumentPublicUrl: vi.fn(
    (_session, tenantId, kind) => `https://api.test/v1/tenants/${tenantId}/legal/${kind}`,
  ),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { LegalModule } from './LegalModule.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Legal', summary: 'Páginas legales' };

const DOCS = {
  documents: [
    {
      id: 'doc-1',
      kind: 'privacy',
      version: 2,
      language: 'es',
      title: 'Política de Privacidad v2',
      published_at: '2026-05-01T10:00:00Z',
      archived_at: null,
      created_at: '2026-05-01T09:00:00Z',
    },
    {
      id: 'doc-2',
      kind: 'terms',
      version: 1,
      language: 'es',
      title: 'Términos v1',
      published_at: null,
      archived_at: null,
      created_at: '2026-05-10T09:00:00Z',
    },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <LegalModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listLegalDocuments.mockResolvedValue(DOCS);
});

describe('LegalModule', () => {
  it('renders the published documents, editor and version history', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Legal', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText('Documentos')).toBeInTheDocument();
    expect(screen.getByText('Editor · Markdown')).toBeInTheDocument();
    expect(screen.getByText('Historial de versiones')).toBeInTheDocument();
    // The published privacy version surfaces in the documents panel.
    expect(await screen.findByText(/v2 — publicado/)).toBeInTheDocument();
    // The unpublished terms version exposes a publish action.
    expect(await screen.findByRole('button', { name: 'Publicar' })).toBeInTheDocument();
  });

  it('live-renders the Markdown preview as the editor textarea changes', async () => {
    setup();
    await screen.findByText('Editor · Markdown');

    await userEvent.type(screen.getByLabelText('Contenido (Markdown)'), '# Hola legal');

    // renderPreview turns the heading into an <h1> inside the preview pane.
    expect(screen.getByRole('heading', { name: 'Hola legal', level: 1 })).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks legal.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Legal', level: 1 })).toBeNull();
  });
});
