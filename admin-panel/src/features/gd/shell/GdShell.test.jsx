import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock del TenantProvider para alimentar supportModeOverride al banner
// embebido — SupportModeBanner usa `useOptionalTenantContext()` para
// resolver el override y el botón "Salir de support mode".
let mockTenantContext = {
  supportModeOverride: null,
  deactivateSupportMode: vi.fn(),
};
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { GdShell } from './GdShell.jsx';

describe('GdShell', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockTenantContext = {
      supportModeOverride: null,
      deactivateSupportMode: vi.fn(),
    };
  });

  it('renderiza wrapper data-testid + children', () => {
    render(
      <GdShell roles={['gd.radicador']}>
        <div data-testid="child">Hola</div>
      </GdShell>,
    );
    expect(screen.getByTestId('gd-shell-root')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('renderiza breadcrumbs cuando se pasan', () => {
    render(
      <GdShell
        roles={['gd.radicador']}
        breadcrumbs={[
          { label: 'Inicio', path: '/gd' },
          { label: 'Ventanilla' },
        ]}
      >
        <p>x</p>
      </GdShell>,
    );
    expect(screen.getByText('Inicio')).toBeInTheDocument();
    expect(screen.getByText('Ventanilla')).toBeInTheDocument();
  });

  it('breadcrumb click dispara onNavigate al path', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <GdShell
        roles={['gd.radicador']}
        onNavigate={onNavigate}
        breadcrumbs={[
          { label: 'Inicio', path: '/gd' },
          { label: 'Ventanilla' },
        ]}
      >
        <p>x</p>
      </GdShell>,
    );
    await user.click(screen.getByText('Inicio'));
    expect(onNavigate).toHaveBeenCalledWith('/gd');
  });

  it('último breadcrumb es "here" (no link)', () => {
    const { container } = render(
      <GdShell
        roles={['gd.radicador']}
        breadcrumbs={[{ label: 'A' }, { label: 'B' }]}
      >
        <p />
      </GdShell>,
    );
    expect(container.querySelector('.here')).toBeTruthy();
  });

  it('data-scope refleja el scope inicial', () => {
    render(
      <GdShell roles={['gd.radicador']} tenantSlug="acme">
        <p />
      </GdShell>,
    );
    expect(screen.getByTestId('gd-shell-root').getAttribute('data-scope')).toBe('propio');
  });

  // BUG-008 / paridad con TenantShell — un platform_owner que entra a GD
  // bajo support_mode necesita seguir viendo el banner para poder salir
  // sin volver al shell del tenant.
  it('renderiza SupportModeBanner cuando hay override activo para el tenant', () => {
    mockTenantContext = {
      supportModeOverride: {
        tenantId: 'tenant-acme',
        expiresAt: new Date(Date.now() + 30 * 60 * 1000),
      },
      deactivateSupportMode: vi.fn(),
    };
    render(
      <GdShell roles={['gd.admin_sistema']} activeTenantId="tenant-acme">
        <p />
      </GdShell>,
    );
    expect(screen.getByText(/Operando en support_mode/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Salir de support mode/i }),
    ).toBeInTheDocument();
  });

  it('no renderiza SupportModeBanner si el override es de otro tenant', () => {
    mockTenantContext = {
      supportModeOverride: {
        tenantId: 'tenant-other',
        expiresAt: new Date(Date.now() + 30 * 60 * 1000),
      },
      deactivateSupportMode: vi.fn(),
    };
    render(
      <GdShell roles={['gd.admin_sistema']} activeTenantId="tenant-acme">
        <p />
      </GdShell>,
    );
    expect(screen.queryByText(/Operando en support_mode/i)).toBeNull();
  });
});
