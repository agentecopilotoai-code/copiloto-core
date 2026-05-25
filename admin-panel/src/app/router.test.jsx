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
  // UI-INFLU-MENU — `TenantShellRoute` consulta este endpoint al montar para
  // decidir si mostrar el item `influencer-entry` en el sidebar. Default `false`
  // en estos tests porque ningún test específico necesita el item.
  isInfluencerEnabled: vi.fn(() => Promise.resolve(false)),
  // GD-MENU — análogo a `isInfluencerEnabled` pero para el módulo de
  // Gestión Documental. Default `false`: el item `gd-entry` no aparece
  // en el sidebar en los tests, y `GdShellRoute` redirige a la home
  // del tenant si se intenta acceder directamente.
  isGdEnabled: vi.fn(() => Promise.resolve(false)),
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

    // BUG-087: ahora 'contacts' aparece en MOBILE_PRIMARY_PRIORITY, así que
    // el botón "Contactos" se renderea TANTO en el sidebar como en el
    // ShellBottomNav (este último oculto en desktop via CSS, pero el DOM
    // existe en jsdom). Usamos el primero (sidebar) para preservar el
    // contrato del test original.
    const buttons = screen.getAllByRole('button', { name: 'Contactos' });
    await user.click(buttons[0]);

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
    // D-ROUTES-01: platform admin movido de `/platform` a `/admin`.
    // El PlatformOwnerShell renderiza el heading desde `activeModule.label`
    // tan pronto monta (`/admin` resuelve `segments[1]` a
    // ROLE_HOME.platform_owner = 'platform-fleet' sync). El pathname
    // solo asienta tras el `<Navigate>` del index — esperamos explícito.
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/admin/platform-fleet');
    });
  });

  it('un usuario de tenant que entra a /admin recibe acceso restringido', async () => {
    renderAt('/admin', { tenants: [ACME(['owner'])] });
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

  it('UI-INFLU-016 — usuario anónimo en `/` ve el PublicLandingShell con tab Ravit activo', async () => {
    // Sin sesión activa → IndexRedirect renderiza <PublicLandingShell
    // activeTab="ravit" /> en lugar de hacer Navigate a /no-tenant o
    // /platform. La ruta permanece en `/`. El landing histórico
    // CopilotoIA queda accesible via `/copiloto` (mismo shell).
    const router = renderAt('/', { session: null, tenants: [] });
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading.textContent).toMatch(/Tu marca/);
    expect(heading.textContent).toMatch(/cara propia/);
    expect(router.state.location.pathname).toBe('/');
  });

  it('UI-INFLU-016 — usuario anónimo en `/copiloto` ve el shell con tab CopilotoIA activo', async () => {
    const router = renderAt('/copiloto', { session: null, tenants: [] });
    const heading = await screen.findByRole('heading', { level: 1 });
    // El tab CopilotoIA monta <Landing embedded /> que mantiene su h1 original.
    expect(heading.textContent).toMatch(/Responde, califica y agenda/);
    expect(router.state.location.pathname).toBe('/copiloto');
  });

  it('UI-017 — el splash legacy ya no se muestra: el copy MVP no aparece para anónimos', async () => {
    // El splash legacy ("Admin Panel MVP" + "Ingresa con Auth0/OIDC para
    // administrar tenants…") fue eliminado en UI-017. La landing es ahora la
    // única vista que ve un usuario anónimo en `/`. Este test bloquea
    // regresiones donde alguien re-introduzca ese splash arriba del router.
    renderAt('/', { session: null, tenants: [] });
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByText(/Admin Panel MVP/i)).toBeNull();
    expect(screen.queryByText(/Ingresa con Auth0\/OIDC/i)).toBeNull();
    expect(screen.queryByRole('link', { name: /Iniciar sesión con Auth0/i })).toBeNull();
  });

  it('mfa_required dispara auto-logout (POST /admin/logout) en lugar del blocker', async () => {
    // Patch del submit del form: en jsdom, form.submit() no navega; con el
    // spy verificamos que se hubiera disparado.
    const submitSpy = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
    try {
      renderAt('/t/acme/services', {
        session: { mfa_required: true, profile: { sub: 'u1', roles: ['owner'] } },
        tenants: [ACME(['owner'])],
      });
      // Tras el render, el useEffect del MfaAutoLogout crea un form y llama submit().
      // El contenido del shell (SERVICES VIEW) no debe aparecer.
      await waitFor(() => expect(submitSpy).toHaveBeenCalled());
      expect(screen.queryByText('SERVICES VIEW')).toBeNull();
      // Verifica que se montó un form apuntando a /admin/logout
      const forms = document.querySelectorAll('form[action*="/admin/logout"]');
      expect(forms.length).toBeGreaterThanOrEqual(1);
    } finally {
      submitSpy.mockRestore();
    }
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

  it('UI-018 — un usuario con rol manager pero caps sólo de agent aterriza en el primer módulo accesible', async () => {
    // Escenario real de UI-018: el JWT trae `manager` pero `tenant.roles` sólo
    // incluye `agent`. `ROLE_HOME.manager === 'manager-analytics'` exige
    // `analytics.tenant.read` que sí la tiene el agent, pero queremos validar
    // que cuando NO la tenga (caso extremo: tenant downgrade), el helper
    // saltea al primer módulo accesible del TENANT_NAV.
    //
    // En esta prueba el usuario tiene rol efectivo `agent` (que en la matriz
    // SÍ tiene `analytics.tenant.read`), así que el ROLE_HOME preferido para
    // el rol más alto (agent) es `operations-desk`, NO `manager-analytics`.
    // El test confirma que el redirect cae a `operations-desk` sin crash, NO
    // a una vista de manager-only.
    const router = renderAt('/', { tenants: [ACME(['agent'])] });
    await screen.findByText('INBOX VIEW');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/t/acme/operations-desk');
    });
  });

  it('UI-018 — un usuario con rol vacío [] ve el StateScreen "Sin acceso a ningún módulo"', async () => {
    // Edge case crítico: `tenant.roles = []` (rol efectivo vacío, p.ej. usuario
    // recién invitado a quien aún no le asignaron rol). Antes el redirect
    // calculaba `home = ROLE_HOME.viewer` y aterrizaba en `viewer-summary`
    // donde el `RequirePermission` con `analytics.tenant.read` cortaba el
    // render dejando pantalla en blanco (BUG-001 / UI-018).
    //
    // Ahora `resolveSafeHomeModule` devuelve null (ningún módulo del VIEWER_NAV
    // es accesible para un rol vacío) y el router pinta el `StateScreen`
    // "Sin acceso a ningún módulo" con CTA de logout.
    const router = renderAt('/', { tenants: [ACME([])] });
    expect(
      await screen.findByRole('heading', { name: 'Sin acceso a ningún módulo' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
    // No redirect: la ruta sigue en `/` mientras el StateScreen está visible.
    expect(router.state.location.pathname).toBe('/');
  });
});
