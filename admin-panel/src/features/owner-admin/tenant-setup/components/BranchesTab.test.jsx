/**
 * Coverage push for BranchesTab — smoke + branch coverage of the
 * `currentTenantId ? <BranchesManager /> : <hint>` conditional.
 *
 * BranchesManager is heavy (fetches data, requires session). We mock it
 * out so this stays a real unit test of BranchesTab's own render logic.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../branches/index.js', () => ({
  BranchesManager: ({ module, session, tenant }) => (
    <div data-testid="branches-manager-mock">
      <span data-testid="branches-manager-module">{module?.label}</span>
      <span data-testid="branches-manager-session">{session?.tenantId ?? 'none'}</span>
      <span data-testid="branches-manager-tenant">{tenant?.id}</span>
    </div>
  ),
}));

import { BranchesTab } from './BranchesTab.jsx';

describe('BranchesTab', () => {
  it('renders the always-visible hint copy', () => {
    render(<BranchesTab state={{ currentTenantId: null }} session={null} />);
    expect(screen.getByText(/Configura una sede para empezar/)).toBeInTheDocument();
  });

  it('shows the "save business first" hint when there is no current tenant id', () => {
    render(<BranchesTab state={{ currentTenantId: null }} session={null} />);
    expect(
      screen.getByText(/Primero guarda los datos del negocio para configurar sedes\./),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('branches-manager-mock')).toBeNull();
  });

  it('renders BranchesManager with the right props when a tenant exists', () => {
    const session = { tenantId: 'sess-1' };
    render(<BranchesTab state={{ currentTenantId: 'tenant-42' }} session={session} />);

    expect(screen.getByTestId('branches-manager-mock')).toBeInTheDocument();
    expect(screen.getByTestId('branches-manager-module')).toHaveTextContent('Sedes');
    expect(screen.getByTestId('branches-manager-session')).toHaveTextContent('sess-1');
    expect(screen.getByTestId('branches-manager-tenant')).toHaveTextContent('tenant-42');
    // the fallback hint is gone when BranchesManager renders
    expect(
      screen.queryByText(/Primero guarda los datos del negocio para configurar sedes\./),
    ).toBeNull();
  });

  it('exposes the data-wizard-tab attribute for navigation helpers', () => {
    const { container } = render(
      <BranchesTab state={{ currentTenantId: 'tenant-x' }} session={{}} />,
    );
    expect(container.querySelector('[data-wizard-tab="branches"]')).toBeInTheDocument();
  });
});
