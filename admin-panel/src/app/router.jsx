import { useEffect, useState } from 'react';
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
import { adminPath } from '../services/adminSession.js';
import { LoadingScreen } from '../components/layout/LoadingScreen.jsx';
import { Button, StateScreen } from '../components/ui/index.js';
import {
  AccountNotifications,
  AccountPreferences,
  AccountProfile,
  AccountSessions,
  AccountShell,
} from '../features/account/index.js';
import { TenantSetupWizard } from '../features/owner-admin/tenant-setup/index.js';
import { PublicLanding } from '../features/public/PublicLanding.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { adminModules } from './modules.js';
import { ModulePlaceholder } from './ModulePlaceholder.jsx';
import {
  AccessDenied,
  computePermissions,
  RequirePermission,
  ROLE_HOME,
  usePermissions,
} from '../permissions/index.js';
import { MODULE_REGISTRY } from './moduleRegistry.js';
import { NoModuleAccessScreen } from './NoModuleAccessScreen.jsx';
import { resolveSafeHomeModule } from './resolveSafeHomeModule.js';
import { PlatformOwnerShell } from './shells/PlatformOwnerShell.jsx';
import { TenantShell } from './shells/TenantShell.jsx';
// Branch `core`: solo PlatformOwnerShell + TenantShell. Los módulos opt-in
// traen su propio shell cuando se instalan sobre el core.
import {
  ACTIVE_TENANT_STORAGE_KEY,
  pickDefaultTenant,
  TenantProvider,
  useTenantContext,
} from './TenantProvider.jsx';

// Branch `core`: en el sistema operativo base solo hay módulos PLATFORM
// (cross-tenant) y TENANT transversales (config). Los módulos de producto
// opt-in registran sus IDs cuando se instalan sobre el core.
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
  const permissions = usePermissions();
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
  const { session, isLoading } = useAuth();
  // BUG-185 (codex P2 sobre BUG-085): `AuthProvider` inicializa `session=null`
  // mientras `fetchAdminSession()` está en flight. Sin este gate, los guards
  // downstream (`NoTenantRoute`/`OnboardingRoute`/`PlatformRoute`) tratan al
  // usuario autenticado en mid-load como anónimo y lo redirigen a `/` —
  // perdiendo el deep link (ej. `/admin/platform/platform-feature-flags`).
  // Mostramos LoadingScreen hasta que el status resuelve a `authenticated` /
  // `anonymous` / `error`. Después el resto del árbol decide qué renderear
  // basado en `session` ya estabilizada.
  if (isLoading) {
    return <LoadingScreen />;
  }
  if (session?.mfa_required === true) {
    // Dev-friendly behavior: en lugar de bloquear el panel con
    // <MfaRequiredBlocker /> y su grace period de 7 días, hacemos auto-logout
    // inmediato. Cada vez que se monte el admin con MFA pendiente, el usuario
    // vuelve a la pantalla de login en lugar de quedarse "atascado" viendo el
    // bloqueo (que en dev local se ve cada restart, no aporta nada nuevo).
    //
    // En producción la palanca real para conservar el blocker original es
    // simplemente revertir este branch y dejar `return <MfaRequiredBlocker />;`.
    return <MfaAutoLogout />;
  }
  return (
    <TenantProvider session={session}>
      <Outlet />
    </TenantProvider>
  );
}

/**
 * Componente "auto-logout" para el caso `session.mfa_required === true`.
 * Al montar, hace POST a `/admin/logout` (invalida la sesión BFF) y la
 * página redirige a la pantalla de login. Mostramos `<LoadingScreen />`
 * mientras tanto para que el usuario no vea un flash en blanco.
 *
 * NOTA: este componente reemplaza al `<MfaRequiredBlocker />` original
 * por una mejor UX en dev: cada vez que se monta un admin fresco, en
 * lugar de mostrar el bloqueo con 7 días de grace period, simplemente
 * desloguea. El `MfaRequiredBlocker` sigue exportado y testeado — no
 * lo elimino para no romper tests; solo cambio el punto de uso.
 */
function MfaAutoLogout() {
  useEffect(() => {
    // Submit oculto del form POST a `/admin/logout`. El BFF invalida la
    // sesión y responde con redirect a la pantalla de login de Auth0
    // (donde si configuran MFA, vuelven a entrar limpios).
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = adminPath('/admin/logout');
    form.style.display = 'none';
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'mfa-auto-logout';
    input.value = '1';
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
  }, []);
  return <LoadingScreen />;
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
  // Permisos calculados en dos contextos:
  //   (a) sin tenant — para decidir si es platform_owner y va a `/platform`.
  //   (b) en el `defaultTenant` — para el safe-home tenant-scoped.
  // `usePermissions()` está atado al tenant del URL (vía `useActiveTenant()`),
  // pero acá el URL es `/` (sin slug). Por eso usamos `computePermissions`
  // (función pura, no-hook) con args explícitos.
  const platformPermissions = computePermissions({ profile, tenant: null });
  const defaultTenant = pickDefaultTenant(tenantOptions);
  const tenantPermissions = computePermissions({ profile, tenant: defaultTenant });

  // Usuario anónimo → landing pública mínima del core (CTA de login).
  if (!session) return <PublicLanding />;

  if (tenantsLoading) return <LoadingScreen />;
  if (platformPermissions.role === 'platform_owner') {
    return <Navigate to="/platform" replace />;
  }
  if (!defaultTenant) return <Navigate to="/no-tenant" replace />;

  // Branch `core`: sin módulos de producto instalados, post-login el
  // usuario aterriza en `tenant-setup` (configuración del tenant). Cuando
  // un módulo se instala, redefine `IndexRedirect` o agrega su entrada
  // a `TENANT_NAV` y `resolveSafeHomeModule` la prioriza.
  void tenantPermissions; // reservado para módulos que filtren por rol
  return <Navigate to={`/t/${defaultTenant.slug}/tenant-setup`} replace />;
}

/** `/no-tenant`: tarjeta de bienvenida para usuarios sin tenant. */
function NoTenantRoute() {
  const { session, tenantOptions, tenantsLoading } = useTenantContext();
  const navigate = useNavigate();
  // BUG-085: usuarios anónimos no deben llegar a `/no-tenant`. Sin esta
  // guarda, `/admin/no-tenant` rendereaba el wizard de signup a cualquiera
  // que tipeara la URL — el backend ya rechaza las requests, pero la UI
  // exponía el formulario y leaks de copy interno.
  if (!session) return <Navigate to="/" replace />;
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
  // BUG-085: usuarios anónimos no deben llegar al onboarding wizard.
  if (!session) return <Navigate to="/" replace />;
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
  const { session, profile, tenantsLoading } = useTenantContext();
  // En `PlatformRoute` la URL es `/platform/...` (sin `tenantSlug`), así que
  // `useActiveTenant()` retorna `null` automáticamente — equivalente al
  // `tenant: null` explícito que se pasaba antes.
  const permissions = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  // BUG-085: usuarios anónimos no deben llegar a `/platform/*`. La guarda
  // de role check (line abajo) NO catchea anon — `permissions.role` puede
  // ser undefined y `!== 'platform_owner'` los frena, PERO la guarda
  // explícita por session es más clara y consistente con NoTenantRoute /
  // OnboardingRoute.
  if (!session) return <Navigate to="/" replace />;
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
  // Branch `core`: sin módulos de producto, el home del tenant es
  // `tenant-setup` (configuración). Cuando se instala un módulo, su
  // entry-point se vuelve el home según `resolveSafeHomeModule`.
  useOutletContext();
  return <Navigate to="tenant-setup" replace />;
}

/**
 * BUG-186 — preservado por compatibilidad con tests que importan
 * `resolveSafeHomeModule`. En el core no hay sub-tree read-only montado.
 * Resultado: aterrizaban en una vista inaccesible → AccessDenied.
 * Ahora delegamos en `resolveSafeHomeModule(permissions)` que itera el
 * `VIEWER_NAV` y devuelve el primer módulo cuya capability el viewer SÍ
 * tiene; si ninguno es accesible, renderea `NoModuleAccessScreen` igual
 * que `TenantHomeRedirect`.
 */
/** Layout tenant-scoped (Owner / Admin / Manager / Agent).
 *
 * Branch `core`: sin módulos opt-in instalados, el sidebar del tenant solo
 * expone la sección "Configuración" (tenant-setup, team). Los módulos de
 * producto se registran al instalarse y se filtran por `tenant_modules`
 * activo.
 */
function TenantShellRoute() {
  const { activeTenant } = useOutletContext();
  const { profile, tenantOptions, session } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, moduleId]
  const activeModuleId = segments[2] || 'tenant-setup';

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
      session={session}
    >
      <Outlet context={{ activeTenant }} />
    </TenantShell>
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
        // Branch `core`: tenant routes minimalistas. Solo TenantShell con
        // los transversales (tenant-setup, team). Los módulos opt-in agregan
        // sub-trees acá cuando se instalan sobre el core (TODO Fase 3 —
        // module discovery).
        path: 't/:tenantSlug',
        element: <TenantScope />,
        children: [
          { index: true, element: <TenantHomeRedirect /> },
          {
            element: <TenantShellRoute />,
            children: [
              ...TENANT_MODULE_IDS.map(moduleRoute),
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
