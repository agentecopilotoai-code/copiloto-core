import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Branch `core`: sin módulos de producto, el MODULE_REGISTRY real solo
// tiene platform-* + transversales (tenant-setup, team, legal, audit).
// Los tests mockean con componentes triviales para aislar el ruteo.
vi.mock('./moduleRegistry.js', () => ({
  MODULE_REGISTRY: {
    'tenant-setup': {
      Component: () => <div>TENANT-SETUP VIEW</div>,
      capability: null,
    },
    team: { Component: () => <div>TEAM VIEW</div>, capability: 'team.write', mode: 'RW' },
    audit: { Component: () => <div>AUDIT VIEW</div>, capability: 'audit.read' },
    legal: { Component: () => <div>LEGAL VIEW</div>, capability: 'legal.write', mode: 'RW' },
    'platform-fleet': {
      Component: () => <div>FLEET VIEW</div>,
      capability: 'platform.tenants.read',
    },
  },
}));

let mockSession;
vi.mock('../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

let mockTenants;
vi.mock('../services/coreApi.js', () => ({
  listMyTenants: vi.fn(() => Promise.resolve(mockTenants)),
}));

// eslint-disable-next-line import/first
import { routes } from './router.jsx';

const ACME = (roles) => ({
  id: 'tenant-acme',
  slug: 'acme',
  display_name: 'Acme Spa',
  roles,
  is_default: true,
});

function renderAt(path, { session = { profile: { sub: 'u1' } }, tenants = [] } = {}) {
  mockSession = session;
  mockTenants = tenants;
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  window.localStorage?.clear();
  mockSession = undefined;
  mockTenants = [];
});

describe('router por rol — branch core', () => {
  it('redirect raíz: un owner aterriza en tenant-setup (sin módulos instalados)', async () => {
    const router = renderAt('/', { tenants: [ACME(['owner'])] });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/t/acme/tenant-setup');
    });
  });

  it('TenantHomeRedirect: /t/{slug} → /t/{slug}/tenant-setup', async () => {
    const router = renderAt('/t/acme', { tenants: [ACME(['owner'])] });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/t/acme/tenant-setup');
    });
  });

  it('deep-link a un módulo transversal del tenant (audit) responde', async () => {
    const router = renderAt('/t/acme/audit', { tenants: [ACME(['owner'])] });
    await screen.findByText('AUDIT VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/audit');
  });

  it('un módulo chatbot legacy (services) NO está registrado → 404', async () => {
    const router = renderAt('/t/acme/services', { tenants: [ACME(['owner'])] });
    expect(
      await screen.findByRole('heading', { name: 'Esta página no existe (o se mudó)' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/t/acme/services');
  });

  it('redirect raíz: un platform owner en support_mode entra a la flota', async () => {
    const router = renderAt('/', {
      session: { profile: { sub: 'po', support_mode: true, roles: ['platform_owner'] } },
      tenants: [],
    });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/platform/platform-fleet');
    });
  });

  it('un usuario de tenant que entra a /platform recibe acceso restringido', async () => {
    renderAt('/platform', { tenants: [ACME(['owner'])] });
    expect(await screen.findByText('Acceso restringido')).toBeInTheDocument();
  });

  it('sin tenant: el redirect raíz lleva a /no-tenant', async () => {
    const router = renderAt('/', { tenants: [] });
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: /Aún no estás asignada a un negocio/,
      }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/no-tenant');
    });
  });

  it('UI-016.6 — una URL desconocida pinta la pantalla 404', async () => {
    const router = renderAt('/some/unknown/path', { tenants: [ACME(['owner'])] });
    expect(
      await screen.findByRole('heading', { name: 'Esta página no existe (o se mudó)' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ir al dashboard' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/some/unknown/path');
  });

  it('mfa_required dispara auto-logout (POST /admin/logout)', async () => {
    const submitSpy = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
    try {
      renderAt('/t/acme/tenant-setup', {
        session: { mfa_required: true, profile: { sub: 'u1', roles: ['owner'] } },
        tenants: [ACME(['owner'])],
      });
      await waitFor(() => expect(submitSpy).toHaveBeenCalled());
      expect(screen.queryByText('TENANT-SETUP VIEW')).toBeNull();
      const forms = document.querySelectorAll('form[action*="/admin/logout"]');
      expect(forms.length).toBeGreaterThanOrEqual(1);
    } finally {
      submitSpy.mockRestore();
    }
  });
});
