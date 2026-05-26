import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Branch `core`: sin módulos de producto, el MODULE_REGISTRY real solo
// tiene platform-* + transversales (tenant-setup, team).
// Los tests mockean con componentes triviales para aislar el ruteo.
vi.mock('./moduleRegistry.js', () => ({
  MODULE_REGISTRY: {
    'tenant-setup': {
      Component: () => <div>TENANT-SETUP VIEW</div>,
      capability: null,
    },
    team: { Component: () => <div>TEAM VIEW</div>, capability: 'team.write', mode: 'RW' },
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

  it('deep-link a un módulo transversal del tenant (team) responde', async () => {
    const router = renderAt('/t/acme/team', { tenants: [ACME(['owner'])] });
    await screen.findByText('TEAM VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/team');
  });

  it('un módulo legacy no registrado → 404', async () => {
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

  it('NotFoundRoute: botón "Reportar enlace roto" navega al mailto', async () => {
    renderAt('/some/unknown/path', { tenants: [ACME(['owner'])] });
    await screen.findByRole('heading', { name: 'Esta página no existe (o se mudó)' });
    const original = window.location;
    // jsdom no permite mutar location.href directamente — usamos Proxy.
    let assignedHref = '';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...original,
        get href() { return original.href; },
        set href(val) { assignedHref = val; },
      },
    });
    try {
      await screen.findByRole('button', { name: 'Reportar enlace roto' });
      const userEvent = (await import('@testing-library/user-event')).default;
      await userEvent.click(screen.getByRole('button', { name: 'Reportar enlace roto' }));
      expect(assignedHref).toMatch(/^mailto:soporte@copilotoia\.co\?subject=/);
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: original,
      });
    }
  });

  it('OnboardingRoute: anónimo redirige a "/"', async () => {
    const router = renderAt('/onboarding', { session: null });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('NoTenantRoute: anónimo redirige a "/"', async () => {
    const router = renderAt('/no-tenant', { session: null });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('NoTenantRoute: usuario con tenants ya activos redirige a "/"', async () => {
    const router = renderAt('/no-tenant', { tenants: [ACME(['owner'])] });
    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe('/no-tenant');
    });
  });

  it('PlatformRoute: anónimo redirige a "/"', async () => {
    const router = renderAt('/platform', { session: null });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('AccountRoute: anónimo redirige a "/"', async () => {
    const router = renderAt('/account/profile', { session: null });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('TenantScope: slug que no matchea ningún tenant redirige a "/"', async () => {
    const router = renderAt('/t/desconocido/team', { tenants: [ACME(['owner'])] });
    await waitFor(() => {
      // El slug no matchea, TenantScope redirige a /
      expect(router.state.location.pathname).not.toBe('/t/desconocido/team');
    });
  });

  it('mfa_required dispara auto-logout (fetch POST /admin/logout)', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 303 });
    const originalFetch = global.fetch;
    global.fetch = fetchSpy;
    const assignSpy = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });
    try {
      renderAt('/t/acme/tenant-setup', {
        session: { mfa_required: true, profile: { sub: 'u1', roles: ['owner'] } },
        tenants: [ACME(['owner'])],
      });
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
        const [url, init] = fetchSpy.mock.calls[0];
        expect(String(url)).toMatch(/\/admin\/logout$/);
        expect(init.method).toBe('POST');
        expect(init.headers['x-requested-with']).toBe('fetch');
        expect(init.credentials).toBe('include');
      });
      expect(screen.queryByText('TENANT-SETUP VIEW')).toBeNull();
    } finally {
      global.fetch = originalFetch;
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });
});
