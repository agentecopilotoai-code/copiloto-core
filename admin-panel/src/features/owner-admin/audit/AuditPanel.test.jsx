import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listAuditLogsFiltered: vi.fn(),
  exportAuditLogs: vi.fn(),
  exportTenantData: vi.fn(),
  suppressContact: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { AuditPanel } from './AuditPanel.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Auditoría', summary: 'Trazabilidad' };

const LOGS = [
  {
    id: 'log-1',
    created_at: '2026-05-14T09:42:00Z',
    actor_type: 'user',
    action: 'legal_document.drafted',
    entity_type: 'legal_document',
    entity_id: 'doc-1',
  },
];

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <AuditPanel module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
  coreApi.listAuditLogsFiltered.mockResolvedValue(LOGS);
});

describe('AuditPanel', () => {
  it('renders the filters, privacy tools and DPA summary', () => {
    setup();

    expect(screen.getByRole('heading', { name: 'Auditoría', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('Filtros')).toBeInTheDocument();
    expect(
      screen.getByText('Supresión de contacto (GDPR / derecho al olvido)'),
    ).toBeInTheDocument();
    expect(screen.getByText('Política de datos (DPA)')).toBeInTheDocument();
    // The log table is not rendered until the first query.
    expect(screen.queryByTestId('audit-table')).toBeNull();
  });

  it('queries the audit logs and renders the results table', async () => {
    setup();

    await userEvent.click(screen.getByRole('button', { name: 'Consultar' }));

    await waitFor(() => expect(coreApi.listAuditLogsFiltered).toHaveBeenCalled());
    expect(await screen.findByTestId('audit-table')).toBeInTheDocument();
    expect(screen.getByText('legal_document.drafted')).toBeInTheDocument();
  });

  it('triggers the CSV export with the current filters', async () => {
    setup();

    await userEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }));

    expect(coreApi.exportAuditLogs).toHaveBeenCalledWith(
      SESSION,
      'tenant-acme',
      expect.not.objectContaining({ limit: expect.anything() }),
    );
  });

  it('renders AccessDenied when the active tenant role lacks audit.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Auditoría', level: 1 })).toBeNull();
  });
});
