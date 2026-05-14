import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// El test del router NO ejercita los módulos reales (tienen sus propios tests).
// Se sustituye el registro por componentes triviales para aislar el ruteo,
// los guards de permiso y los redirects por rol.
vi.mock('./moduleRegistry.js', () => ({
  MODULE_REGISTRY: {
    services: {
      Component: () => <div>SERVICES VIEW</div>,
      capability: 'services.read',
      mode: 'R',
    },
    contacts: { Component: () => <div>CONTACTS VIEW</div>, capability: 'contacts.view' },
    analytics: {
      Component: () => <div>ANALYTICS VIEW</div>,
      capability: 'analytics.tenant.read',
    },
    team: { Component: () => <div>TEAM VIEW</div>, capability: 'team.write', mode: 'RW' },
    'operations-desk': {
      Component: () => <div>INBOX VIEW</div>,
      capability: 'conversations.view',
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

describe('router por rol', () => {
  it('deep-link: un owner que recarga /t/acme/services aterriza en esa vista', async () => {
    const router = renderAt('/t/acme/services', { tenants: [ACME(['owner'])] });
    expect(await screen.findByText('SERVICES VIEW')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/t/acme/services');
  });

  it('navegar entre módulos cambia la URL', async () => {
    const user = userEvent.setup();
    const router = renderAt('/t/acme/services', { tenants: [ACME(['owner'])] });
    await screen.findByText('SERVICES VIEW');

    await user.click(screen.getByRole('button', { name: 'Contactos' }));

    expect(await screen.findByText('CONTACTS VIEW')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/t/acme/contacts');
  });

  it('un agent navegando a una vista sin permiso recibe el componente 403, no pantalla blanca', async () => {
    const router = renderAt('/t/acme/team', { tenants: [ACME(['agent'])] });
    expect(await screen.findByText('Acceso restringido')).toBeInTheDocument();
    expect(screen.queryByText('TEAM VIEW')).toBeNull();
    // La ruta se resolvió: no es un white screen ni un 404.
    expect(router.state.location.pathname).toBe('/t/acme/team');
  });

  it('redirect raíz: un owner aterriza en su home de rol (analítica)', async () => {
    const router = renderAt('/', { tenants: [ACME(['owner'])] });
    expect(await screen.findByText('ANALYTICS VIEW')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/t/acme/analytics');
  });

  it('redirect raíz: un viewer entra al shell de solo lectura', async () => {
    const router = renderAt('/', { tenants: [ACME(['viewer'])] });
    await screen.findByText('ANALYTICS VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/read/analytics');
  });

  it('redirect raíz: un platform owner en support_mode entra a la flota', async () => {
    const router = renderAt('/', {
      session: { profile: { sub: 'po', support_mode: true, roles: ['platform_owner'] } },
      tenants: [],
    });
    expect(
      await screen.findByRole('heading', { name: 'Fleet · Tenants', level: 1 }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/platform/platform-fleet');
  });

  it('un usuario de tenant que entra a /platform recibe acceso restringido', async () => {
    renderAt('/platform', { tenants: [ACME(['owner'])] });
    expect(await screen.findByText('Acceso restringido')).toBeInTheDocument();
  });

  it('sin tenant: el redirect raíz lleva a /no-tenant', async () => {
    const router = renderAt('/', { tenants: [] });
    expect(await screen.findByText('Crea tu tenant para empezar')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/no-tenant');
  });

  it('mfa_required bloquea cualquier ruta con el gate de MFA', async () => {
    renderAt('/t/acme/services', {
      session: { mfa_required: true, profile: { sub: 'u1', roles: ['owner'] } },
      tenants: [ACME(['owner'])],
    });
    expect(
      await screen.findByRole('heading', { name: /Verificación en dos pasos obligatoria/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText('SERVICES VIEW')).toBeNull();
  });

  it('un slug de tenant desconocido vuelve al redirect raíz', async () => {
    const router = renderAt('/t/desconocido/services', { tenants: [ACME(['owner'])] });
    // /t/desconocido no existe → Navigate('/') → home del owner.
    await screen.findByText('ANALYTICS VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/analytics');
  });
});
