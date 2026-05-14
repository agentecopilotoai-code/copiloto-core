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
import { ModulePlaceholder } from '../components/modules/ModulePlaceholder.jsx';
import { TenantSetupWizard } from '../components/modules/tenantSetup/TenantSetupWizard.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { adminModules } from '../data/modules.js';
import { AccessDenied, RequirePermission, ROLE_HOME, usePermissions } from '../permissions/index.js';
import { MODULE_REGISTRY } from './moduleRegistry.js';
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
 * Redirect raíz `/` → home por rol:
 *   - platform owner (support_mode) → `/platform`,
 *   - sin tenant                    → `/no-tenant`,
 *   - viewer                        → `/t/:slug/read`,
 *   - resto                         → `/t/:slug/:roleHome`.
 */
function IndexRedirect() {
  const { profile, tenantOptions, tenantsLoading } = useTenantContext();
  const platformPermissions = usePermissions({ profile, tenant: null });
  const defaultTenant = pickDefaultTenant(tenantOptions);
  const tenantPermissions = usePermissions({ profile, tenant: defaultTenant });

  if (tenantsLoading) return <LoadingScreen />;
  if (platformPermissions.role === 'platform_owner') {
    return <Navigate to="/platform" replace />;
  }
  if (!defaultTenant) return <Navigate to="/no-tenant" replace />;

  const base = `/t/${defaultTenant.slug}`;
  if (tenantPermissions.role === 'viewer') {
    return <Navigate to={`${base}/read`} replace />;
  }
  return <Navigate to={`${base}/${tenantPermissions.home}`} replace />;
}

/** `/no-tenant`: tarjeta de bienvenida para usuarios sin tenant. */
function NoTenantRoute() {
  const { tenantOptions, tenantsLoading } = useTenantContext();
  const navigate = useNavigate();
  if (tenantsLoading) return <LoadingScreen />;
  if (tenantOptions.length > 0) return <Navigate to="/" replace />;
  return <NoTenantOnboarding onCreateTenant={() => navigate('/onboarding')} />;
}

/** `/onboarding`: wizard de creación del primer tenant (sin shell). */
function OnboardingRoute() {
  const { session, handleTenantCreated } = useTenantContext();
  const navigate = useNavigate();
  const module = adminModules.find((item) => item.id === 'tenant-setup');
  return (
    <TenantSetupWizard
      module={module}
      session={session}
      tenant={null}
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

/** Index de `/t/:tenantSlug` → home por rol dentro del tenant. */
function TenantHomeRedirect() {
  const { activeTenant } = useOutletContext();
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: activeTenant });
  if (permissions.role === 'viewer') return <Navigate to="read" replace />;
  return <Navigate to={permissions.home} replace />;
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
  const activeModuleId = segments[3] || 'analytics';
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
              { index: true, element: <Navigate to="analytics" replace /> },
              ...TENANT_MODULE_IDS.map(moduleRoute),
            ],
          },
          {
            element: <TenantShellRoute />,
            children: TENANT_MODULE_IDS.map(moduleRoute),
          },
        ],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
];

/** Router de producción. `base` de Vite es `/admin/` → `basename: '/admin'`. */
export const appRouter = createBrowserRouter(routes, { basename: '/admin' });
