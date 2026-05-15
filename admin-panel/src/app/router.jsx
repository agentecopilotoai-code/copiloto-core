import { useEffect } from 'react';
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useOutletContext,
  useParams,
  useSearchParams,
} from 'react-router-dom';

import { MfaRequiredBlocker } from '../components/domain/MfaRequiredBlocker.jsx';
import { NoTenantOnboarding } from '../components/domain/NoTenantOnboarding.jsx';
import { LoadingScreen } from '../components/layout/LoadingScreen.jsx';
import { Button, StateScreen } from '../components/ui/index.js';
import {
  AccountNotifications,
  AccountPreferences,
  AccountProfile,
  AccountSessions,
  AccountShell,
} from '../features/account/index.js';
import { ContactProfile } from '../features/agente/contact-profile/index.js';
import { TenantSetupWizard } from '../features/owner-admin/tenant-setup/index.js';
import { Landing } from '../features/public/landing/index.js';
import { useAuth } from '../context/AuthContext.jsx';
import { adminModules } from './modules.js';
import { ModulePlaceholder } from './ModulePlaceholder.jsx';
import { AccessDenied, RequirePermission, ROLE_HOME, usePermissions } from '../permissions/index.js';
import { MODULE_REGISTRY } from './moduleRegistry.js';
import { NoModuleAccessScreen } from './NoModuleAccessScreen.jsx';
import { resolveSafeHomeModule } from './resolveSafeHomeModule.js';
import { PlatformOwnerShell } from './shells/PlatformOwnerShell.jsx';
import { ReadOnlyShell } from './shells/ReadOnlyShell.jsx';
import { TenantShell } from './shells/TenantShell.jsx';
import {
  ACTIVE_TENANT_STORAGE_KEY,
  pickDefaultTenant,
  TenantProvider,
  useTenantContext,
} from './TenantProvider.jsx';

const PLATFORM_MODULE_IDS = adminModules
  .filter((module) => module.id.startsWith('platform-'))
  .map((module) => module.id);

const TENANT_MODULE_IDS = adminModules
  .filter((module) => !module.id.startsWith('platform-'))
  .map((module) => module.id);

/**
 * Renderiza el componente de un `module id`, envuelto en `<RequirePermission>`
 * cuando el registro declara una `capability`. Reemplaza al `switch` de
 * `ModuleContent.jsx`. Los ids sin entrada en el registro caen a
 * `<ModulePlaceholder/>` (vistas pendientes de UI-006..UI-010).
 *
 * @param {{ moduleId: string }} props
 */
function ModuleScreen({ moduleId }) {
  const outletContext = useOutletContext();
  const activeTenant = outletContext?.activeTenant ?? null;
  const { profile, session, handleTenantCreated } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: activeTenant });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const module = adminModules.find((item) => item.id === moduleId);
  const entry = MODULE_REGISTRY[moduleId];

  if (!entry) {
    return <ModulePlaceholder module={module} tenant={activeTenant} />;
  }

  const { Component, capability, mode = 'R' } = entry;
  const extraProps = {};
  if (moduleId === 'tenant-setup') {
    extraProps.initialTab = searchParams.get('tab');
    extraProps.onTenantCreated = handleTenantCreated;
  } else if (moduleId === 'onboarding-wizard') {
    extraProps.onNavigateToModule = (id) => navigate(`/t/${activeTenant.slug}/${id}`);
  } else if (moduleId === 'go-live-readiness') {
    extraProps.onGoToEscalation = () =>
      navigate(`/t/${activeTenant.slug}/tenant-setup?tab=escalation`);
  }

  const content = (
    <Component module={module} session={session} tenant={activeTenant} {...extraProps} />
  );

  if (!capability) return content;
  return (
    <RequirePermission permissions={permissions} capability={capability} mode={mode}>
      {content}
    </RequirePermission>
  );
}

/**
 * Raíz del router: aplica el gate de MFA (TASK-0080 / BUG14) antes de montar
 * cualquier vista y provee la lista de tenants al resto del árbol.
 */
function RootLayout() {
  const { session } = useAuth();
  if (session?.mfa_required === true) {
    return <MfaRequiredBlocker />;
  }
  return (
    <TenantProvider session={session}>
      <Outlet />
    </TenantProvider>
  );
}

/**
 * Resuelve `/`:
 *   - sin sesión (anónimo)          → `<Landing />` (UI-016.4),
 *   - platform owner (support_mode) → `/platform`,
 *   - sin tenant                    → `/no-tenant`,
 *   - viewer                        → `/t/:slug/read/<safe-home>`,
 *   - resto                         → `/t/:slug/<safe-home>`.
 *
 * Cuando `session === null` (usuario no autenticado) la app muestra la landing
 * comercial pública en lugar de redirigir a Auth0. La landing tiene su propio
 * CTA "Iniciar sesión" que dispara el flow Auth0 existente.
 *
 * **UI-018 — Fallback seguro de home:** antes calculábamos el home con
 * `tenantPermissions.home` (= `ROLE_HOME[role]`), pero esa key apuntaba a un
 * módulo cuya capability el usuario podía NO tener en su tenant activo (caso
 * típico: roles globales vía JWT desincronizados con `tenant.roles` —
 * TASK-0077). Resultado: post-login el usuario aterrizaba en una vista a la
 * que su rol no tenía acceso → `RequirePermission` cortaba el render → pantalla
 * en blanco / "error de autenticación". Ahora delegamos en
 * `resolveSafeHomeModule(permissions)` que devuelve el ROLE_HOME preferido si
 * la cap es accesible o, en su defecto, el primer módulo accesible del nav
 * visual (`TENANT_NAV` / `VIEWER_NAV`). Si NADA es accesible (rol vacío),
 * pintamos un `StateScreen` "Sin acceso a ningún módulo" con CTA de logout
 * en lugar de hacer redirect a un módulo roto.
 */
function IndexRedirect() {
  const { session, profile, tenantOptions, tenantsLoading } = useTenantContext();
  const platformPermissions = usePermissions({ profile, tenant: null });
  const defaultTenant = pickDefaultTenant(tenantOptions);
  const tenantPermissions = usePermissions({ profile, tenant: defaultTenant });

  // Usuario anónimo → landing pública. Sin RequirePermission (es público).
  if (!session) return <Landing />;

  if (tenantsLoading) return <LoadingScreen />;
  if (platformPermissions.role === 'platform_owner') {
    return <Navigate to="/platform" replace />;
  }
  if (!defaultTenant) return <Navigate to="/no-tenant" replace />;

  const base = `/t/${defaultTenant.slug}`;
  const safeHome = resolveSafeHomeModule(tenantPermissions);

  if (!safeHome) {
    // UI-018 — rol efectivo sin acceso a NINGÚN módulo en el tenant activo.
    // En vez de redirigir a una vista que va a fallar el guard, mostramos un
    // estado claro con CTA para cerrar sesión y reintentar con otra cuenta.
    return <NoModuleAccessScreen />;
  }

  if (tenantPermissions.role === 'viewer') {
    return <Navigate to={`${base}/read/${safeHome}`} replace />;
  }
  return <Navigate to={`${base}/${safeHome}`} replace />;
}

/** `/no-tenant`: tarjeta de bienvenida para usuarios sin tenant. */
function NoTenantRoute() {
  const { tenantOptions, tenantsLoading } = useTenantContext();
  const navigate = useNavigate();
  if (tenantsLoading) return <LoadingScreen />;
  if (tenantOptions.length > 0) return <Navigate to="/" replace />;
  return <NoTenantOnboarding onCreateTenant={() => navigate('/onboarding')} />;
}

/**
 * `/account/*` (UI-016.7): rutas transversales detrás del avatar del sidebar.
 * No requieren tenant activo — solo sesión autenticada. Si el usuario es
 * anónimo, el `IndexRedirect` ya cubre `/` con la landing pública; `/account`
 * directo sin sesión reenvía a la raíz para que `IndexRedirect` decida.
 */
function AccountRoute() {
  const { session } = useTenantContext();
  if (!session) return <Navigate to="/" replace />;
  return <AccountShell />;
}

/** `/onboarding`: wizard de creación del primer tenant (sin shell). */
function OnboardingRoute() {
  const { session, handleTenantCreated } = useTenantContext();
  const navigate = useNavigate();
  const module = adminModules.find((item) => item.id === 'tenant-setup');
  // BUG-002 fix: initialSignup={true} skips the wizard's tenant_setup.write
  // RequirePermission gate. The user reaches this route from /no-tenant with
  // zero tenant memberships, so they have no roles and would always crash
  // into AccessDenied. The backend's tenant-signup endpoint is the actual
  // security boundary.
  return (
    <TenantSetupWizard
      module={module}
      session={session}
      tenant={null}
      initialSignup
      onTenantCreated={(tenant) => {
        handleTenantCreated(tenant);
        if (tenant?.slug) navigate(`/t/${tenant.slug}`);
      }}
    />
  );
}

/** `/platform`: shell de flota. Guard: rol efectivo `platform_owner`. */
function PlatformRoute() {
  const { profile, tenantsLoading } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const navigate = useNavigate();
  const location = useLocation();

  if (tenantsLoading) return <LoadingScreen />;
  if (permissions.role !== 'platform_owner') {
    return <AccessDenied capability="platform.tenants.read" mode="R" />;
  }

  const segments = location.pathname.split('/').filter(Boolean); // ['platform', moduleId]
  const activeModuleId = segments[1] || ROLE_HOME.platform_owner;
  const activeModule =
    adminModules.find((item) => item.id === activeModuleId) ?? adminModules[0];

  return (
    <PlatformOwnerShell
      profile={profile}
      permissions={permissions}
      modules={adminModules}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={(id) => navigate(`/platform/${id}`)}
    >
      <Outlet />
    </PlatformOwnerShell>
  );
}

/**
 * `/t/:tenantSlug`: resuelve el tenant activo desde el slug de la URL y lo
 * propaga vía `Outlet context`. Persiste el último tenant visitado para el
 * redirect raíz. Si el slug no corresponde a ningún tenant del usuario,
 * vuelve a `/`.
 */
function TenantScope() {
  const { tenantOptions, tenantsLoading } = useTenantContext();
  const { tenantSlug } = useParams();
  const activeTenant = tenantOptions.find((tenant) => tenant.slug === tenantSlug) ?? null;

  useEffect(() => {
    if (!activeTenant) return;
    try {
      window.localStorage?.setItem(ACTIVE_TENANT_STORAGE_KEY, activeTenant.id);
    } catch {
      /* ignore storage errors */
    }
  }, [activeTenant]);

  if (tenantsLoading) return <LoadingScreen />;
  if (!activeTenant) return <Navigate to="/" replace />;
  return <Outlet context={{ activeTenant }} />;
}

/**
 * Index de `/t/:tenantSlug` → home por rol dentro del tenant. UI-018: aplica
 * el mismo fallback seguro que `IndexRedirect` (vía `resolveSafeHomeModule`)
 * para evitar redirigir a un módulo cuya capability el usuario no tenga en
 * ESTE tenant en particular (puede diferir del default tenant).
 */
function TenantHomeRedirect() {
  const { activeTenant } = useOutletContext();
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: activeTenant });
  const safeHome = resolveSafeHomeModule(permissions);
  if (!safeHome) return <NoModuleAccessScreen />;
  if (permissions.role === 'viewer') return <Navigate to={`read/${safeHome}`} replace />;
  return <Navigate to={safeHome} replace />;
}

/** Layout tenant-scoped (Owner / Admin / Manager / Agent). */
function TenantShellRoute() {
  const { activeTenant } = useOutletContext();
  const { profile, tenantOptions } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: activeTenant });
  const navigate = useNavigate();
  const location = useLocation();

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, moduleId]
  const activeModuleId = segments[2] || permissions.home;

  // Un viewer nunca entra al shell con CTAs de escritura: aunque el módulo
  // permita lectura (ej. analytics, contacts), se redirige al subárbol
  // read-only que aplica el chrome de solo lectura y oculta las acciones.
  if (permissions.role === 'viewer') {
    return <Navigate to={`/t/${activeTenant.slug}/read/${activeModuleId}`} replace />;
  }

  const activeModule =
    adminModules.find((item) => item.id === activeModuleId) ?? adminModules[0];

  return (
    <TenantShell
      profile={profile}
      permissions={permissions}
      modules={adminModules}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={(id) => navigate(`/t/${activeTenant.slug}/${id}`)}
      tenantOptions={tenantOptions}
      activeTenantId={activeTenant.id}
      onTenantChange={(id) => {
        const next = tenantOptions.find((tenant) => tenant.id === id);
        if (next) navigate(`/t/${next.slug}`);
      }}
      canSwitchTenants={tenantOptions.length > 1 || permissions.isSystemOwner}
    >
      <Outlet context={{ activeTenant }} />
    </TenantShell>
  );
}

/** Layout de solo lectura (Viewer). */
function ReadOnlyShellRoute() {
  const { activeTenant } = useOutletContext();
  const { profile, tenantOptions } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: activeTenant });
  const navigate = useNavigate();
  const location = useLocation();

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, 'read', moduleId]
  const activeModuleId = segments[3] || ROLE_HOME.viewer;
  const activeModule =
    adminModules.find((item) => item.id === activeModuleId) ?? adminModules[0];

  return (
    <ReadOnlyShell
      profile={profile}
      permissions={permissions}
      modules={adminModules}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={(id) => navigate(`/t/${activeTenant.slug}/read/${id}`)}
      tenantOptions={tenantOptions}
      activeTenantId={activeTenant.id}
      onTenantChange={(id) => {
        const next = tenantOptions.find((tenant) => tenant.id === id);
        if (next) navigate(`/t/${next.slug}/read`);
      }}
      canSwitchTenants={tenantOptions.length > 1 || permissions.isSystemOwner}
    >
      <Outlet context={{ activeTenant }} />
    </ReadOnlyShell>
  );
}

/**
 * UI-016.6 — pantalla 404 para el catch-all `path: '*'`. Reemplaza el
 * `<Navigate to="/" replace />` silencioso anterior: ahora una URL inválida
 * muestra el mensaje "Esta página no existe (o se mudó)" del HTML T2, con
 * dos CTAs claros ("Ir al dashboard" + "Reportar enlace roto") en lugar de
 * un redirect invisible.
 */
function NotFoundRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const subject = encodeURIComponent(`Enlace roto en ${location.pathname}`);
  const reportHref = `mailto:soporte@copilotoia.co?subject=${subject}`;
  return (
    <StateScreen
      tone="neutral"
      icon={<NotFoundIcon />}
      heading="Esta página no existe (o se mudó)"
      body={
        <p>
          La URL que abriste (<code>{location.pathname}</code>) no apunta a
          ningún módulo del panel. Revisa el link o vuelve al dashboard de tu
          tenant.
        </p>
      }
      primary={
        <Button variant="primary" onClick={() => navigate('/')}>
          Ir al dashboard
        </Button>
      }
      secondary={
        <Button
          variant="ghost"
          onClick={() => {
            if (typeof window !== 'undefined') {
              window.location.href = reportHref;
            }
          }}
        >
          Reportar enlace roto
        </Button>
      }
    />
  );
}

function NotFoundIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3-3" />
    </svg>
  );
}

const moduleRoute = (id) => ({ path: id, element: <ModuleScreen moduleId={id} /> });

/**
 * Árbol de rutas declarativo por rol. Exportado para que los tests lo monten
 * con `createMemoryRouter`.
 */
export const routes = [
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <IndexRedirect /> },
      { path: 'login', element: <Navigate to="/" replace /> },
      { path: 'no-tenant', element: <NoTenantRoute /> },
      { path: 'onboarding', element: <OnboardingRoute /> },
      {
        path: 'account',
        element: <AccountRoute />,
        children: [
          { index: true, element: <Navigate to="profile" replace /> },
          { path: 'profile', element: <AccountProfile /> },
          { path: 'preferences', element: <AccountPreferences /> },
          { path: 'notifications', element: <AccountNotifications /> },
          { path: 'sessions', element: <AccountSessions /> },
        ],
      },
      {
        path: 'platform',
        element: <PlatformRoute />,
        children: [
          { index: true, element: <Navigate to={ROLE_HOME.platform_owner} replace /> },
          ...PLATFORM_MODULE_IDS.map(moduleRoute),
        ],
      },
      {
        path: 't/:tenantSlug',
        element: <TenantScope />,
        children: [
          { index: true, element: <TenantHomeRedirect /> },
          {
            path: 'read',
            element: <ReadOnlyShellRoute />,
            children: [
              { index: true, element: <Navigate to={ROLE_HOME.viewer} replace /> },
              ...TENANT_MODULE_IDS.map(moduleRoute),
            ],
          },
          {
            element: <TenantShellRoute />,
            children: [
              ...TENANT_MODULE_IDS.map(moduleRoute),
              // UI-009.3 — deep-link a la ficha enfocada de un contacto. No es
              // un módulo (no aparece en la nav); `contacts/:contactId` es una
              // ruta más profunda que el módulo `contacts` exacto, así que no
              // colisiona. `ContactProfile` aplica su propio `<RequirePermission
              // capability="contacts.view">`, por eso no se envuelve en
              // `<ModuleScreen>`.
              { path: 'contacts/:contactId', element: <ContactProfile /> },
            ],
          },
        ],
      },
      { path: '*', element: <NotFoundRoute /> },
    ],
  },
];

/** Router de producción. `base` de Vite es `/admin/` → `basename: '/admin'`. */
export const appRouter = createBrowserRouter(routes, { basename: '/admin' });
