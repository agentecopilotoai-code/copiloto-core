import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listContactSegments: vi.fn(),
  createContactSegment: vi.fn(),
  updateContactSegment: vi.fn(),
  deleteContactSegment: vi.fn(),
  previewContactSegment: vi.fn(),
  refreshContactSegment: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { SegmentsModule } from './SegmentsModule.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['manager'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Segmentos', summary: 'Retención y reactivación' };

const SEGMENTS = [
  {
    id: 'seg-1',
    name: 'Sin visita en 60+ días',
    description: 'Reactivación',
    kind: 'dynamic',
    contact_count: 42,
    last_refreshed_at: '2026-05-10T12:00:00Z',
    is_system: true,
    rules: { all_of: [{ field: 'last_appointment_at', op: 'lt_days_ago', value: 60 }] },
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <SegmentsModule module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listContactSegments.mockResolvedValue(SEGMENTS);
});

describe('SegmentsModule', () => {
  it('renders the segments list for a manager', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Segmentos', level: 1 }),
    ).toBeInTheDocument();
    // The segment name appears in the list row and in the preview panel header.
    expect((await screen.findAllByText('Sin visita en 60+ días')).length).toBeGreaterThan(0);
    expect(screen.getByText('Segmentos (1)')).toBeInTheDocument();
    await waitFor(() => expect(coreApi.listContactSegments).toHaveBeenCalled());
  });

  it('opens the create segment drawer from the header CTA', async () => {
    setup();
    await screen.findAllByText('Sin visita en 60+ días');

    await userEvent.click(screen.getByRole('button', { name: 'Nuevo segmento' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nuevo segmento');
    expect(screen.getByRole('button', { name: 'Crear segmento' })).toBeInTheDocument();
  });

  it('renders the dynamic rule builder inside the create drawer', async () => {
    setup();
    await screen.findAllByText('Sin visita en 60+ días');

    await userEvent.click(screen.getByRole('button', { name: 'Nuevo segmento' }));

    await screen.findByRole('dialog');
    // The rule builder fieldset + a default rule row are present.
    expect(screen.getByRole('group', { name: 'Reglas' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Campo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Añadir regla' })).toBeInTheDocument();
  });

  it('renders AccessDenied when the active tenant role lacks segments.write', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Segmentos', level: 1 })).toBeNull();
  });
});
