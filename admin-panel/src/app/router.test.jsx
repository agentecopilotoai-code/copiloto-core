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
    dashboard: {
      Component: () => <div>DASHBOARD VIEW</div>,
      capability: 'analytics.tenant.read',
    },
    team: { Component: () => <div>TEAM VIEW</div>, capability: 'team.write', mode: 'RW' },
    'operations-desk': {
      Component: () => <div>INBOX VIEW</div>,
      capability: 'conversations.view',
    },
    'viewer-summary': {
      Component: () => <div>VIEWER SUMMARY VIEW</div>,
      capability: 'analytics.tenant.read',
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

  it('redirect raíz: un owner aterriza en su home de rol (dashboard)', async () => {
    const router = renderAt('/', { tenants: [ACME(['owner'])] });
    expect(await screen.findByText('DASHBOARD VIEW')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/t/acme/dashboard');
  });

  it('redirect raíz: un viewer entra al shell de solo lectura', async () => {
    const router = renderAt('/', { tenants: [ACME(['viewer'])] });
    // UI-010.1: el home del Viewer es `viewer-summary` (era `analytics`).
    await screen.findByText('VIEWER SUMMARY VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/read/viewer-summary');
  });

  it('un viewer con deep-link al shell de escritura es redirigido a /read', async () => {
    // El módulo permite lectura al viewer, pero el shell con CTAs de escritura
    // no: debe aterrizar en el subárbol read-only conservando el módulo.
    const router = renderAt('/t/acme/analytics', { tenants: [ACME(['viewer'])] });
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
    // The PlatformOwnerShell renders the heading from `activeModule.label` as
    // soon as `/platform` mounts (the index route resolves `segments[1]` to
    // ROLE_HOME.platform_owner = 'platform-fleet' synchronously). The actual
    // pathname only settles after the index `<Navigate>` completes — under
    // Node 20 + coverage instrumentation that second hop can lag behind the
    // DOM render. Wait for it explicitly.
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
    // UI-016.6: el copy del HTML T2 ahora es "Aún no estás asignada a un
    // negocio"; el literal legacy "Crea tu tenant para empezar" se conserva
    // como microcopy dentro del body (envuelto en <strong>), así que se
    // busca con regex (texto fraccionado entre nodos).
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: /Aún no estás asignada a un negocio/,
      }),
    ).toBeInTheDocument();
    // Same race-resilience as the platform-owner redirect above: the DOM can
    // settle before the IndexRedirect <Navigate> finishes propagating into
    // `router.state.location.pathname` under coverage instrumentation.
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/no-tenant');
    });
  });

  it('UI-016.4 — usuario anónimo en `/` ve la landing pública (no redirect)', async () => {
    // Sin sesión activa → IndexRedirect renderiza <Landing /> en lugar de
    // hacer Navigate a /no-tenant o /platform. La ruta permanece en `/`.
    const router = renderAt('/', { session: null, tenants: [] });
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading.textContent).toMatch(/Responde, califica y agenda/);
    expect(heading.textContent).toMatch(/en segundos/);
    expect(router.state.location.pathname).toBe('/');
  });

  it('mfa_required bloquea cualquier ruta con el gate de MFA', async () => {
    renderAt('/t/acme/services', {
      session: { mfa_required: true, profile: { sub: 'u1', roles: ['owner'] } },
      tenants: [ACME(['owner'])],
    });
    // UI-016.6: el heading pasó del literal "Verificación en dos pasos
    // obligatoria" al copy del HTML T2 "Activa autenticación de dos factores".
    expect(
      await screen.findByRole('heading', { name: /Activa autenticación de dos factores/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText('SERVICES VIEW')).toBeNull();
  });

  it('UI-016.6 — una URL desconocida pinta la pantalla 404 (sin redirect silencioso)', async () => {
    const router = renderAt('/some/unknown/path', { tenants: [ACME(['owner'])] });
    // Antes el catch-all hacía Navigate('/'); ahora muestra el StateScreen 404
    // con el copy del HTML T2 y la URL inválida en el body.
    expect(
      await screen.findByRole('heading', { name: 'Esta página no existe (o se mudó)' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ir al dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reportar enlace roto' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/some/unknown/path');
  });

  it('un slug de tenant desconocido vuelve al redirect raíz', async () => {
    const router = renderAt('/t/desconocido/services', { tenants: [ACME(['owner'])] });
    // /t/desconocido no existe → Navigate('/') → home del owner.
    await screen.findByText('DASHBOARD VIEW');
    expect(router.state.location.pathname).toBe('/t/acme/dashboard');
  });
});
