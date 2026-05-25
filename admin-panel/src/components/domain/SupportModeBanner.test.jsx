import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { SupportModeBanner } from './SupportModeBanner.jsx';

const FUTURE = new Date(Date.now() + 30 * 60 * 1000); // 30 min en el futuro

beforeEach(() => {
  mockTenantContext = {
    supportModeOverride: null,
    deactivateSupportMode: vi.fn().mockResolvedValue(undefined),
  };
});

describe('SupportModeBanner (BUG-008)', () => {
  it('no renderiza nada si no hay override activo', () => {
    const { container } = render(<SupportModeBanner activeTenantId="tenant-acme" />);
    expect(container.firstChild).toBeNull();
  });

  it('no renderiza si el override.tenantId NO matchea el activeTenantId', () => {
    // El cookie es scoped a UN tenant. Si el user navega a otro, el banner
    // NO debe aparecer aunque el override esté activo para otro tenant.
    mockTenantContext = {
      ...mockTenantContext,
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: FUTURE },
    };
    const { container } = render(<SupportModeBanner activeTenantId="tenant-other" />);
    expect(container.firstChild).toBeNull();
  });

  it('renderiza el banner cuando override matchea activeTenantId', () => {
    mockTenantContext = {
      ...mockTenantContext,
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: FUTURE },
    };
    render(<SupportModeBanner activeTenantId="tenant-acme" />);
    expect(screen.getByText(/Operando en support_mode/i)).toBeInTheDocument();
    expect(screen.getByText(/Expira en/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Salir de support mode/i }),
    ).toBeInTheDocument();
  });

  it('invoca deactivateSupportMode al hacer click en "Salir"', async () => {
    const deactivate = vi.fn().mockResolvedValue(undefined);
    mockTenantContext = {
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: FUTURE },
      deactivateSupportMode: deactivate,
    };
    render(<SupportModeBanner activeTenantId="tenant-acme" />);
    await userEvent.click(
      screen.getByRole('button', { name: /Salir de support mode/i }),
    );
    expect(deactivate).toHaveBeenCalledWith('tenant-acme');
  });

  it('invoca onExited después de deactivateSupportMode exitoso', async () => {
    // Sin esto, el platform_owner dentro de GdShell/InfluencerShell queda
    // en una página rota porque la cookie ya no existe y las queries 404.
    const deactivate = vi.fn().mockResolvedValue(undefined);
    const onExited = vi.fn();
    mockTenantContext = {
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: FUTURE },
      deactivateSupportMode: deactivate,
    };
    render(
      <SupportModeBanner activeTenantId="tenant-acme" onExited={onExited} />,
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Salir de support mode/i }),
    );
    expect(deactivate).toHaveBeenCalledWith('tenant-acme');
    expect(onExited).toHaveBeenCalledTimes(1);
  });

  it('no invoca onExited si deactivateSupportMode falla', async () => {
    // Si el server rechaza el DELETE (ej. red caída), no navegamos —
    // mejor dejar al user en la página con error visible que llevarlo
    // a /platform "como si todo hubiera salido bien".
    const deactivate = vi.fn().mockRejectedValue(new Error('network'));
    const onExited = vi.fn();
    mockTenantContext = {
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: FUTURE },
      deactivateSupportMode: deactivate,
    };
    render(
      <SupportModeBanner activeTenantId="tenant-acme" onExited={onExited} />,
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Salir de support mode/i }),
    );
    expect(onExited).not.toHaveBeenCalled();
  });

  it('compara tenantId como string — UUID-like distinto tipo igual matchea', () => {
    // Si el activeTenantId llega como number-ish y el override como string,
    // el banner debe matchear igual (ambos lados normalizan con String()).
    mockTenantContext = {
      ...mockTenantContext,
      supportModeOverride: { tenantId: '12345', expiresAt: FUTURE },
    };
    render(<SupportModeBanner activeTenantId={12345} />);
    expect(screen.getByText(/Operando en support_mode/i)).toBeInTheDocument();
  });

  it('muestra "Expira pronto" cuando el TTL ya venció', () => {
    // Defensa contra UI engañosa: si el cookie ya expiró server-side, el
    // backend va a rechazar las siguientes requests. El banner avisa al user
    // para que re-active si necesita más tiempo.
    const past = new Date(Date.now() - 60 * 1000);
    mockTenantContext = {
      ...mockTenantContext,
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: past },
    };
    render(<SupportModeBanner activeTenantId="tenant-acme" />);
    expect(screen.getByText(/Expira pronto/)).toBeInTheDocument();
  });
});
