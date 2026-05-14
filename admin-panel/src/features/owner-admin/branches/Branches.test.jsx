import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listBranches: vi.fn(),
  createBranch: vi.fn(),
  updateBranch: vi.fn(),
  deactivateBranch: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Branches } from './Branches.jsx';
// eslint-disable-next-line import/first
import { BranchesManager } from './BranchesManager.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Sedes', summary: 'Ubicaciones físicas' };

const BRANCHES = [
  {
    id: 'br-1',
    name: 'Sede Chapinero',
    code: 'principal',
    address: 'Cra. 13 # 85-21',
    city: 'Bogotá',
    phone_e164: '+5714821900',
    timezone: 'America/Bogota',
    opening_hours: { mon: [{ start: '09:00', end: '19:00' }] },
    is_active: true,
  },
  {
    id: 'br-2',
    name: 'Sede Usaquén',
    code: 'usaquen',
    address: 'Cl. 116 # 7A-15',
    city: 'Bogotá',
    timezone: 'America/Bogota',
    opening_hours: {},
    is_active: true,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listBranches.mockResolvedValue(BRANCHES);
});

describe('BranchesManager', () => {
  it('renders the branch cards with the Principal badge and schedule summary', async () => {
    render(<BranchesManager module={MODULE} session={SESSION} tenant={ACME} />);

    expect(
      await screen.findByRole('heading', { name: 'Sedes', level: 1 }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Sede Chapinero')).toBeInTheDocument();
    expect(screen.getByText('Sede Usaquén')).toBeInTheDocument();
    expect(screen.getByText('Principal')).toBeInTheDocument();
    expect(screen.getByText('Lun 09:00-19:00')).toBeInTheDocument();
    expect(screen.getByText('Sin horario configurado')).toBeInTheDocument();
  });

  it('opens the create drawer from the page header CTA', async () => {
    render(<BranchesManager module={MODULE} session={SESSION} tenant={ACME} />);
    await screen.findByText('Sede Chapinero');

    await userEvent.click(screen.getByRole('button', { name: 'Nueva sede' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Nueva sede');
    expect(screen.getByRole('button', { name: 'Crear sede' })).toBeInTheDocument();
    // The opening-hours editor is part of the drawer.
    expect(screen.getByTestId('branches-hours')).toBeInTheDocument();
  });

  it('opens the edit drawer pre-filled when a branch is edited', async () => {
    render(<BranchesManager module={MODULE} session={SESSION} tenant={ACME} />);
    await screen.findByText('Sede Chapinero');

    await userEvent.click(screen.getAllByRole('button', { name: 'Editar' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('Editar sede');
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('Sede Chapinero')).toBeInTheDocument();
  });
});

describe('Branches (gated entry)', () => {
  it('renders AccessDenied when the active tenant role lacks branches.write', () => {
    render(
      <MemoryRouter>
        <Branches
          module={MODULE}
          session={SESSION}
          tenant={{ id: 'tenant-acme', slug: 'acme', roles: ['agent'] }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Sedes', level: 1 })).toBeNull();
  });

  it('renders the manager when the active tenant role has branches.write', async () => {
    render(
      <MemoryRouter>
        <Branches module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole('heading', { name: 'Sedes', level: 1 }),
    ).toBeInTheDocument();
  });
});
