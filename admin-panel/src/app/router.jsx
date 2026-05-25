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
import { ContactProfile } from '../features/agente/contact-profile/index.js';
import { TenantSetupWizard } from '../features/owner-admin/tenant-setup/index.js';
import { Landing } from '../features/public/landing/index.js';
import { PublicLandingShell } from '../features/public/ravit-landing/PublicLandingShell.jsx';
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
import { ReadOnlyShell } from './shells/ReadOnlyShell.jsx';
import { TenantShell } from './shells/TenantShell.jsx';
import { InfluencerShell } from './shells/InfluencerShell.jsx';
import { isInfluencerEnabled, isGdEnabled } from '../services/coreApi.js';
import { resolveGdRoute } from '../features/gd/routeMap.js';
import { getMyGdProfile } from '../features/gd/services/gdApi.js';
import { GdProvider } from '../features/gd/shell/GdContext.jsx';
import {
  gdHome, gdAdmin,
  influencerHome, chatbotHome,
  legacyRedirectFor,
} from './urls.js';
import { PersonaWizardContainer } from '../features/influencer/wizard/PersonaWizardContainer.jsx';
import { CreatePersonaAndRedirect } from '../features/influencer/wizard/CreatePersonaAndRedirect.jsx';
import { PersonaStudioContainer } from '../features/influencer/studio/PersonaStudioContainer.jsx';
import { GenerateContainer } from '../features/influencer/generate/GenerateContainer.jsx';
import {
  ACTIVE_TENANT_STORAGE_KEY,
  pickDefaultTenant,
  TenantProvider,
  useTenantContext,
} from './TenantProvider.jsx';

const PLATFORM_MODULE_IDS = adminModules
  .filter((module) => module.id.startsWith('platform-'))
  .map((module) => module.id);

// UI-INFLU-002: los módulos `influencer-*` viven bajo un shell distinto
// (`InfluencerShell` con su propio `INFLUENCER_NAV`), por eso los excluimos
// de `TENANT_MODULE_IDS` para que `TenantShellRoute` no intente renderizarlos.
// EXCEPCIÓN: `influencer-entry` SÍ vive en el shell del tenant — es solo un
// item de nav que redirige al InfluencerShell. Necesita una route para que
// el deep-link directo `/t/{slug}/influencer-entry` resuelva al component
// `InfluencerEntryRedirect` (que hace `<Navigate to=".../influencer"/>`).
const INFLUENCER_MODULE_IDS = adminModules
  .filter((module) => module.id.startsWith('influencer-') && module.id !== 'influencer-entry')
  .map((module) => module.id);

const TENANT_MODULE_IDS = adminModules
  .filter(
    (module) =>
      !module.id.startsWith('platform-') &&
      (!module.id.startsWith('influencer-') || module.id === 'influencer-entry'),
  )
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
function IndexRedirect({ publicTab = 'ravit' }) {
  const { session, profile, tenantOptions, tenantsLoading } = useTenantContext();
  // Caso especial: evaluamos permisos en DOS contextos:
  //   (a) sin tenant — para decidir si es platform_owner y va a `/platform`.
  //   (b) en el `defaultTenant` — para resolver el safe-home tenant-scoped.
  // El hook `usePermissions()` está atado al tenant del URL (vía
  // `useActiveTenant()`), pero acá el URL es `/` (sin slug). Por eso usamos
  // `computePermissions` (función pura, no-hook) con args explícitos.
  const platformPermissions = computePermissions({ profile, tenant: null });
  const defaultTenant = pickDefaultTenant(tenantOptions);
  const tenantPermissions = computePermissions({ profile, tenant: defaultTenant });

  // Usuario anónimo → landing pública con shell de tabs.
  // `/` = Personajes AI · `/copiloto` = Chatbot AI · `/documentos` =
  // Gestión Documental AI. Sin RequirePermission (es público).
  if (!session) return <PublicLandingShell activeTab={publicTab} />;

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
  // `usePermissions()` auto-resuelve profile (del TenantContext) y tenant
  // (del slug del URL). El outlet context se conserva por si algún hijo
  // del Route lo necesita downstream.
  useOutletContext();
  const permissions = usePermissions();
  const safeHome = resolveSafeHomeModule(permissions);
  if (!safeHome) return <NoModuleAccessScreen />;
  if (permissions.role === 'viewer') return <Navigate to={`read/${safeHome}`} replace />;
  return <Navigate to={safeHome} replace />;
}

/**
 * BUG-186 (codex P2 sobre BUG-084): index del subárbol `/t/:slug/read/`
 * para viewers. Antes era un `<Navigate to={ROLE_HOME.viewer}>` estático,
 * que redirigía a `viewer-summary` aunque el rol efectivo no tuviera
 * `analytics.tenant.read` (caso edge: viewer con caps customizadas).
 * Resultado: aterrizaban en una vista inaccesible → AccessDenied.
 * Ahora delegamos en `resolveSafeHomeModule(permissions)` que itera el
 * `VIEWER_NAV` y devuelve el primer módulo cuya capability el viewer SÍ
 * tiene; si ninguno es accesible, renderea `NoModuleAccessScreen` igual
 * que `TenantHomeRedirect`.
 */
function ReadHomeRedirect() {
  useOutletContext();
  const permissions = usePermissions();
  const safeHome = resolveSafeHomeModule(permissions);
  if (!safeHome) return <NoModuleAccessScreen />;
  return <Navigate to={safeHome} replace />;
}

/** Layout tenant-scoped (Owner / Admin / Manager / Agent). */
function TenantShellRoute() {
  const { activeTenant } = useOutletContext();
  // BUG-191: extraer `session` del contexto para threadearlo al shell →
  // ShellTopbar → TenantBrandLogo (fetch del logo proxy con Bearer auth).
  const { profile, tenantOptions, session } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, moduleId]
  const activeModuleId = segments[2] || permissions.home;

  // UI-INFLU-MENU — `influencer-entry` aparece en `TENANT_NAV` SOLO si el
  // tenant tiene el módulo influencer habilitado en `app.tenant_modules`.
  // Consultamos `isInfluencerEnabled` al montar (mismo patrón que
  // `InfluencerShellRoute`) y filtramos `adminModules` antes de pasarlos al
  // shell — `resolveNav` excluye los items cuyo `id` no esté en `modules`,
  // así el item desaparece del sidebar sin tocar `resolveNav` ni el shell.
  //
  // `null` = loading (asumimos NO habilitado para no flickear el item);
  // `true` = mostrar; `false` = ocultar.
  const [influencerEnabled, setInfluencerEnabled] = useState(null);
  useEffect(() => {
    if (!session || !activeTenant?.id) return undefined;
    let cancelled = false;
    isInfluencerEnabled(session, activeTenant.id)
      .then((enabled) => {
        if (!cancelled) setInfluencerEnabled(enabled);
      })
      .catch(() => {
        if (!cancelled) setInfluencerEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, activeTenant?.id]);

  // GD-MENU — mismo patrón que influencer: el item `gd-entry` aparece
  // en `TENANT_NAV` SOLO si el tenant tiene Gestión Documental
  // habilitada en `app.tenant_modules.gestion_documental`. Sin esto,
  // el sidebar mostraría una opción que choca con un 404 al entrar.
  const [gdEnabled, setGdEnabled] = useState(null);
  useEffect(() => {
    if (!session || !activeTenant?.id) return undefined;
    let cancelled = false;
    isGdEnabled(session, activeTenant.id)
      .then((enabled) => {
        if (!cancelled) setGdEnabled(enabled);
      })
      .catch(() => {
        if (!cancelled) setGdEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, activeTenant?.id]);

  // Un viewer nunca entra al shell con CTAs de escritura: aunque el módulo
  // permita lectura (ej. analytics, contacts), se redirige al subárbol
  // read-only que aplica el chrome de solo lectura y oculta las acciones.
  if (permissions.role === 'viewer') {
    return <Navigate to={`/t/${activeTenant.slug}/read/${activeModuleId}`} replace />;
  }

  const activeModule =
    adminModules.find((item) => item.id === activeModuleId) ?? adminModules[0];

  // Si los módulos opt-in NO están habilitados (o aún cargando),
  // filtramos sus entries de la lista que recibe el shell — así el
  // nav no los renderiza. Las capabilities (`influencer.module.access`,
  // `gd.module.access`) ya definidas siguen aplicándose por `resolveNav`
  // para roles sin acceso.
  let modulesForShell = adminModules;
  if (!influencerEnabled) {
    modulesForShell = modulesForShell.filter((m) => m.id !== 'influencer-entry');
  }
  if (!gdEnabled) {
    modulesForShell = modulesForShell.filter((m) => m.id !== 'gd-entry');
  }

  return (
    <TenantShell
      profile={profile}
      permissions={permissions}
      modules={modulesForShell}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={(id) => {
        // `influencer-entry` no es un módulo del shell del tenant — es un
        // entry-point al `InfluencerShell`. Navegamos al sub-tree del shell
        // del influencer en lugar de a `/t/{slug}/influencer-entry`. El
        // path `influencer-entry` SÍ tiene route registrada (`TENANT_MODULE_IDS`
        // lo incluye) que monta `InfluencerEntryRedirect` para deep-links
        // directos; este shortcut evita el redirect intermedio.
        if (id === 'influencer-entry') {
          navigate(`/t/${activeTenant.slug}/influencer`);
          return;
        }
        // `gd-entry`: mismo shortcut que influencer — el sub-shell
        // del módulo GD vive en `/t/{slug}/gd`, no en `/t/{slug}/gd-entry`.
        if (id === 'gd-entry') {
          navigate(`/t/${activeTenant.slug}/gd`);
          return;
        }
        navigate(`/t/${activeTenant.slug}/${id}`);
      }}
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
 * UI-INFLU-002 — Layout del módulo Influencer / Ravit Studio.
 *
 * Igual que `TenantShellRoute` (extrae tenant del slug + permisos + navega),
 * pero usa `InfluencerShell` con `INFLUENCER_NAV`. Adicionalmente:
 *   - Consulta `isInfluencerEnabled(session, tenantId)` al montar y guarda
 *     el resultado en estado. Si el backend responde 404 (módulo no activo
 *     para el tenant), el shell muestra un `<AlertBanner>` "Módulo no
 *     habilitado" en lugar del módulo real (decisión D2 — frontend traduce
 *     el 404 a UX amistosa sin filtrar la existencia del feature).
 *   - El estado inicial `null` significa "cargando"; mostramos `<LoadingScreen>`.
 *   - El gate primario sigue siendo el backend; el frontend solo respeta
 *     su veredicto. Si en una venta futura el tenant pierde el módulo, el
 *     primer 404 del próximo request lo refleja.
 */
function InfluencerShellRoute() {
  const { activeTenant } = useOutletContext();
  const { profile, tenantOptions, session } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  // null = loading; true = activo; false = 404 del backend.
  const [moduleEnabled, setModuleEnabled] = useState(null);

  useEffect(() => {
    if (!session || !activeTenant?.id) return undefined;
    let cancelled = false;
    isInfluencerEnabled(session, activeTenant.id)
      .then((enabled) => {
        if (!cancelled) setModuleEnabled(enabled);
      })
      .catch(() => {
        // Cualquier error que NO sea 404 → tratamos como "no activo" para
        // no bloquear la UI. El ErrorBoundary atrapa los crashes reales.
        if (!cancelled) setModuleEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, activeTenant?.id]);

  // Mientras se resuelve la activación, mostramos loading screen sin shell —
  // evita el flash de "Módulo no habilitado" en el primer render.
  if (moduleEnabled === null) return <LoadingScreen />;

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, 'influencer', moduleId]
  const activeModuleId = segments[3] || 'influencer-casting';
  const activeModule =
    adminModules.find((item) => item.id === activeModuleId) ??
    adminModules.find((item) => item.id === 'influencer-casting') ??
    null;

  return (
    <InfluencerShell
      profile={profile}
      permissions={permissions}
      modules={adminModules}
      activeModule={activeModule}
      activeModuleId={activeModuleId}
      onModuleSelect={(id) => navigate(`/t/${activeTenant.slug}/influencer/${id}`)}
      tenantOptions={tenantOptions}
      activeTenantId={activeTenant.id}
      onTenantChange={(id) => {
        const next = tenantOptions.find((tenant) => tenant.id === id);
        if (next) navigate(`/t/${next.slug}/influencer`);
      }}
      canSwitchTenants={tenantOptions.length > 1 || permissions.isSystemOwner}
      session={session}
      moduleEnabled={moduleEnabled}
    >
      <Outlet context={{ activeTenant }} />
    </InfluencerShell>
  );
}

/**
 * Layout del módulo Gestión Documental (GD).
 *
 * Vive PARALELO a `TenantShellRoute` (no anidado dentro) porque el
 * módulo es autocontenido: usa su propio `GdShell` con `GdSidebar`
 * y `GdTopBar` rol-aware. La activación se chequea con
 * `isGdEnabled(session, tenantId)` (mismo patrón que Influencer).
 *
 * Resolución del sub-tree `/t/{slug}/gd/...`:
 *  - El path interno (todo lo que sigue a `/t/{slug}/gd`) se mapea a
 *    un componente con `resolveGdRoute()` (ver `features/gd/routeMap.js`).
 *  - El gate primario es el backend (404 → módulo no activo). El
 *    frontend traduce 404 a UX amistosa sin filtrar la existencia.
 *  - `null` inicial = loading; mostramos `<LoadingScreen />` para
 *    evitar el flash de "no habilitado" en el primer render.
 *
 * Decisión D-WIRE-01: `GdShellRoute` usa el sub-shell completo del
 * módulo (con su sidebar) en lugar de embedar las vistas dentro de
 * `TenantShell`. Razón: el módulo GD tiene 94 vistas y un sidebar
 * rol-aware muy distinto al del producto principal (CopilotoIA);
 * fusionarlos contaminaría ambos. El item `gd-entry` del sidebar
 * tenant simplemente redirige acá.
 */
/**
 * GdShellRoute — shell del módulo GD montado en el ESQUEMA NUEVO
 * (D-ROUTES-01):
 *   mode='op'    → `/gd/t/{slug}/*`        (operación)
 *   mode='admin' → `/gd/admin/t/{slug}/*`  (admin del módulo)
 *
 * Antes vivía como hijo de `TenantScope` y recibía `activeTenant` por
 * outletContext. Ahora resolvemos el tenant directamente desde
 * `useParams().tenantSlug` para que la ruta pueda montar al top-level
 * del router sin depender de la jerarquía anterior.
 */
function GdShellRoute({ mode = 'op' }) {
  const { tenantSlug } = useParams();
  const { tenantOptions, tenantsLoading, profile, session } = useTenantContext();
  const navigate = useNavigate();
  const location = useLocation();

  const activeTenant = tenantOptions.find((t) => t.slug === tenantSlug) ?? null;

  // null = loading; true = activo; false = 404 del backend.
  const [moduleEnabled, setModuleEnabled] = useState(null);

  // Persistimos el último tenant visitado — el redirect raíz lo usa para
  // restaurar contexto. Antes lo hacía TenantScope; ahora cada module
  // route lo hace por su cuenta porque no hay un wrapper compartido.
  useEffect(() => {
    if (!activeTenant) return;
    try {
      window.localStorage?.setItem(ACTIVE_TENANT_STORAGE_KEY, activeTenant.id);
    } catch { /* ignore storage errors */ }
  }, [activeTenant]);

  useEffect(() => {
    if (!session || !activeTenant?.id) return undefined;
    let cancelled = false;
    isGdEnabled(session, activeTenant.id)
      .then((enabled) => {
        if (!cancelled) setModuleEnabled(enabled);
      })
      .catch(() => {
        if (!cancelled) setModuleEnabled(false);
      });
    return () => { cancelled = true; };
  }, [session, activeTenant?.id]);

  if (tenantsLoading) return <LoadingScreen />;
  if (!activeTenant) return <Navigate to="/" replace />;

  if (moduleEnabled === null) return <LoadingScreen />;

  if (moduleEnabled === false) {
    // Módulo no habilitado para este tenant — caemos al chatbot del
    // tenant (home razonable; resolveSafeHomeModule corrige si tampoco
    // tiene acceso ahí).
    return <Navigate to={chatbotHome(activeTenant.slug)} replace />;
  }

  return (
    <GdProfileLoader
      mode={mode}
      session={session}
      activeTenant={activeTenant}
      profile={profile}
      location={location}
      navigate={navigate}
    />
  );
}

/**
 * Loader que resuelve los roles GD del usuario actual antes de renderizar
 * el componente de la ruta. Mientras carga muestra `<LoadingScreen />`.
 * Si el usuario NO tiene perfil GD activo en el tenant, pasa `roles=[]`
 * — el `GdShell` muestra el sidebar vacío y la landing dice "Sin permisos
 * activos. Solicite activación a su administrador."
 */
function GdProfileLoader({ mode = 'op', session, activeTenant, profile, location, navigate }) {
  const [gdMe, setGdMe] = useState(undefined); // undefined=loading, null=sin perfil, {...}=ok

  useEffect(() => {
    if (!session || !activeTenant?.id) return undefined;
    let cancelled = false;
    getMyGdProfile(session)
      .then((data) => {
        if (!cancelled) setGdMe(data || null);
      })
      .catch(() => {
        if (!cancelled) setGdMe(null);
      });
    return () => { cancelled = true; };
  }, [session, activeTenant?.id]);

  if (gdMe === undefined) return <LoadingScreen />;

  const gdRoles = (gdMe?.roles_gd_vigentes || gdMe?.roles_vigentes || [])
    .map((r) => r.rol_codigo)
    .filter(Boolean);

  // basePath del shell — depende del modo. Para mode='op' →
  // `/gd/t/{slug}`; para mode='admin' → `/gd/admin/t/{slug}`. El
  // subPath se calcula stripping ese prefijo del pathname actual.
  const basePath = mode === 'admin' ? gdAdmin(activeTenant.slug) : gdHome(activeTenant.slug);
  let subPath = location.pathname.startsWith(basePath)
    ? location.pathname.slice(basePath.length)
    : '';
  if (subPath === '/') subPath = '';

  const { Component, extraProps } = resolveGdRoute({ mode, subPath });

  // `onNavigate` acepta TRES formas de path para back-compat con todas
  // las páginas históricas:
  //   1. URL absoluta nueva: `/gd/t/{slug}/buzon` → navigate directo.
  //   2. Path legacy `/gd/...` o `/gd/admin/...` → re-componer con el
  //      slug actual via gdHome/gdAdmin (auto-promote interno).
  //   3. Path relativo `'buzon'` → anidar dentro del basePath actual.
  // Sin esto, breadcrumbs hardcodeados como `{ path: '/gd' }` en 50+
  // páginas mandan al usuario a `/gd` (sin slug, 404 garantizado).
  const onNavigate = (path) => {
    if (!path) return;
    if (path === '/gd' || path.startsWith('/gd/')) {
      const subPath = path === '/gd' ? '' : path.slice(3);
      // gdHome promueve `/admin/...` automáticamente a gdAdmin.
      navigate(gdHome(activeTenant.slug, subPath));
      return;
    }
    if (path.startsWith('/')) {
      navigate(path);
    } else {
      navigate(`${basePath}/${path}`);
    }
  };

  return (
    <GdProvider
      user={profile}
      roles={gdRoles}
      session={session}
      tenantSlug={activeTenant.slug}
      activeTenantId={activeTenant.id}
    >
      <Component
        session={session}
        roles={gdRoles}
        user={profile}
        tenantSlug={activeTenant.slug}
        // BUG-008 — `SupportModeBanner` necesita el UUID.
        activeTenantId={activeTenant.id}
        // Salir de support_mode: navegamos a la home del admin tenant
        // del platform_owner. Antes era /platform; ahora /admin.
        onExitSupportMode={() => navigate('/admin')}
        currentPath={location.pathname}
        onNavigate={onNavigate}
        {...extraProps}
      />
    </GdProvider>
  );
}

/** Layout de solo lectura (Viewer). */
function ReadOnlyShellRoute() {
  const { activeTenant } = useOutletContext();
  // BUG-191: thread `session` para que `TenantBrandLogo` pueda fetchear el
  // logo proxy con auth headers (Bearer + X-Tenant-Id).
  const { profile, tenantOptions, session } = useTenantContext();
  const permissions = usePermissions();
  const navigate = useNavigate();
  const location = useLocation();

  const segments = location.pathname.split('/').filter(Boolean); // ['t', slug, 'read', moduleId]
  // BUG-084: usar `resolveSafeHomeModule(permissions)` cuando no hay segment
  // explícito, igual que IndexRedirect. Antes `ROLE_HOME.viewer` apuntaba a
  // un módulo cuya capability el viewer podía no tener en este tenant
  // (TASK-0077 desincronía de roles globales vs tenant.roles) → pantalla en
  // blanco o AccessDenied bajo el ReadOnlyShell.
  const safeHome = resolveSafeHomeModule(permissions);
  const activeModuleId = segments[3] || safeHome || ROLE_HOME.viewer;
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
      session={session}
    >
      <Outlet context={{ activeTenant }} />
    </ReadOnlyShell>
  );
}

/**
 * LegacyTenantRedirect — redirect transparente del esquema viejo
 * `/t/{slug}/{module}/...` al nuevo `/{module}/t/{slug}/...`
 * (D-ROUTES-01). Mantiene bookmarks funcionando durante la transición.
 *
 * Si la URL no es legacy migratable (ej. `/t/{slug}/read/*` que sigue
 * sin migrar) cae al NotFound estándar.
 */
function LegacyTenantRedirect() {
  const location = useLocation();
  const newPath = legacyRedirectFor(location.pathname);
  if (newPath) return <Navigate to={newPath + location.search} replace />;
  // No migra (ej. /t/{slug}/read/...) — delegamos al render del shell
  // original que ya está montado debajo en la misma route tree.
  return <Outlet />;
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
      { index: true, element: <IndexRedirect publicTab="ravit" /> },
      // Tabs públicas: cada ruta reusa el mismo IndexRedirect pero
      // activando el tab correspondiente. Si hay sesión, delegan al
      // mismo flujo de home redirect (igual que `/no-tenant`).
      { path: 'copiloto',   element: <IndexRedirect publicTab="copiloto" /> },
      { path: 'documentos', element: <IndexRedirect publicTab="documentos" /> },
      // Back-compat de la spec previa de UI-INFLU-016 que mencionaba /ravit.
      { path: 'ravit', element: <Navigate to="/" replace /> },
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
      // ─── D-ROUTES-01: rutas top-level por módulo ─────────────────────────
      //
      // Esquema nuevo (canónico):
      //   /gd/t/:slug/*           → operación GD
      //   /gd/admin/t/:slug/*     → admin del módulo GD
      //   /influencer/t/:slug/*   → operación Influencer  (TODO Phase 2)
      //   /chatbot/t/:slug/*      → operación Chatbot     (TODO Phase 2)
      //   /admin/*                → platform admin        (TODO Phase 2)
      //
      // Cada route resuelve `tenantSlug` por su cuenta (no más wrapper
      // TenantScope compartido). La operación y el admin del mismo módulo
      // comparten shell (`GdShellRoute`) parametrizado por `mode`.
      //
      // El orden importa: las rutas más específicas primero
      // (`/gd/admin/t/...` antes de `/gd/t/...` antes de wildcards).
      { path: 'gd/admin/t/:tenantSlug',   element: <GdShellRoute mode="admin" /> },
      { path: 'gd/admin/t/:tenantSlug/*', element: <GdShellRoute mode="admin" /> },
      { path: 'gd/t/:tenantSlug',         element: <GdShellRoute mode="op" /> },
      { path: 'gd/t/:tenantSlug/*',       element: <GdShellRoute mode="op" /> },
      // ─── Legacy redirect ────────────────────────────────────────────────
      //
      // Cualquier URL bajo `/t/:slug/*` que tenga equivalente en el esquema
      // nuevo se redirige (helper `legacyRedirectFor`). Lo que NO migra
      // (read shell, tenant home `/t/:slug` sin módulo) cae a la route
      // original más abajo.
      {
        path: 't/:tenantSlug/*',
        element: <LegacyTenantRedirect />,
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
              // BUG-186: usar `ReadHomeRedirect` (calcula `safeHome` con
              // `resolveSafeHomeModule`) en lugar de un `<Navigate>` estático
              // a `ROLE_HOME.viewer`. Sin esto, viewers con caps customizadas
              // que no incluyen `analytics.tenant.read` aterrizaban en
              // `viewer-summary` y veían AccessDenied.
              { index: true, element: <ReadHomeRedirect /> },
              ...TENANT_MODULE_IDS.map(moduleRoute),
            ],
          },
          {
            // UI-INFLU-002 — sub-tree del módulo Influencer / Ravit Studio.
            // Vive PARALELO a TenantShellRoute (no anidado dentro) porque
            // tiene su propio shell con sub-nav distinta (INFLUENCER_NAV).
            // El gate de activación del módulo (404 del backend) se chequea
            // dentro de `InfluencerShellRoute` con `isInfluencerEnabled`.
            path: 'influencer',
            element: <InfluencerShellRoute />,
            children: [
              {
                index: true,
                element: <Navigate to="influencer-casting" replace />,
              },
              ...INFLUENCER_MODULE_IDS.map(moduleRoute),
              // UI-INFLU-008..012 wiring — wizard de creación de personaje.
              // UI-INFLU-014.11: cada personaje tiene su propio URL con
              // `personaId`. Esto permite que el usuario tenga N drafts
              // en paralelo, cada uno con su propia "página".
              //
              //   `personas/new` → CastingNewPersona (crea draft + redirige).
              //   `personas/:personaId/wizard/:stepSlug` → wizard del draft.
              //
              // Ruta legacy `personas/new/:stepSlug` se mantiene por
              // compat de bookmarks; redirige al casting si no hay un
              // personaId activo en sessionStorage.
              {
                path: 'personas/new',
                element: <CreatePersonaAndRedirect />,
              },
              {
                path: 'personas/new/:stepSlug',
                element: <PersonaWizardContainer />,
              },
              {
                path: 'personas/:personaId/wizard',
                element: <Navigate to="step-1" replace />,
              },
              {
                path: 'personas/:personaId/wizard/:stepSlug',
                element: <PersonaWizardContainer />,
              },
              // UI-INFLU-005 wiring — vista de detalle del personaje.
              // El componente `PersonaStudio` recibe el bundle del
              // endpoint `GET /personas/{id}/studio` resuelto por
              // `PersonaStudioContainer`.
              {
                path: 'personas/:personaId/studio',
                element: <PersonaStudioContainer />,
              },
              // UI-INFLU-013 wiring — composer "Generar contenido".
              {
                path: 'personas/:personaId/generate',
                element: <GenerateContainer />,
              },
            ],
          },
          {
            // Sub-tree del módulo Gestión Documental — PARALELO al
            // tenant shell. Resolución del path interno se hace en
            // `GdShellRoute` mediante `resolveGdRoute(subPath)`. El
            // catch-all `gd/*` cubre todas las vistas (94 vistas + N
            // rutas con UUID), así no tenemos que enumerar cada una
            // acá. El gate por tenant (`isGdEnabled`) y el filtro de
            // permisos por rol se aplican dentro de la route + el
            // sidebar del módulo.
            path: 'gd',
            element: <GdShellRoute />,
          },
          {
            path: 'gd/*',
            element: <GdShellRoute />,
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
