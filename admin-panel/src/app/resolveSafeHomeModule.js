/**
 * UI-018 — Fallback seguro al calcular el "home" post-login.
 *
 * El `IndexRedirect` (router.jsx) usaba `permissions.home` (= `ROLE_HOME[role]`)
 * para decidir a qué módulo aterrizar. El problema: `ROLE_HOME[role]` apunta a
 * un módulo cuya capability puede NO estar disponible para el usuario en su
 * tenant activo. Ejemplo real (síntoma de prod): un usuario con `manager` en su
 * JWT pero `agent` en `tenant.roles` aterrizaba en `manager-analytics`, cuya
 * capability `analytics.tenant.read` el agent SÍ tiene en lectura — pero la
 * desincronía entre roles globales y tenant.roles (TASK-0077) podía dejar al
 * usuario en pantalla blanca cuando el rol efectivo era `[]` o sólo cubría
 * módulos distintos al home preferido.
 *
 * `resolveSafeHomeModule(permissions)` aplica esta secuencia:
 *
 *   1. Lee `ROLE_HOME[permissions.role]`. Si la capability de ese módulo en el
 *      `MODULE_REGISTRY` es accesible para el usuario (`permissions.can(cap,
 *      mode)` o no exige capability), devuelve ese module id.
 *   2. Si NO, itera `TENANT_NAV` (o `VIEWER_NAV` cuando el rol efectivo es
 *      `viewer`) RESPETANDO el orden de las secciones y los items. Devuelve el
 *      PRIMER module id cuya capability sea accesible.
 *   3. Si ningún módulo es accesible (rol vacío `[]` o sin caps en este
 *      tenant), devuelve `null`. El consumidor (router) renderiza un
 *      `StateScreen` "Sin acceso a ningún módulo" en lugar de mostrar el
 *      módulo y dejar que falle el guard interno.
 *
 * **Importante:** la fuente de orden es `nav.js`, NO `moduleRegistry.js`. El
 * orden del registry es un detalle de implementación (alfabético / por
 * import); `nav.js` refleja la jerarquía visual que ve el usuario.
 *
 * **Por qué vive en `app/` y no en `permissions/`:** el helper necesita
 * `MODULE_REGISTRY` (de `app/moduleRegistry.js`) y `TENANT_NAV` / `VIEWER_NAV`
 * (de `app/nav.js`). El `moduleRegistry` importa features que a su vez
 * importan `permissions/index.js` para leer `ROLES` (ej. `RolesAcl` de
 * platform). Exportarlo desde `permissions/index.js` crearía un ciclo
 * `permissions/index → app/moduleRegistry → features → permissions/index`
 * que rompe la inicialización ESM en Vitest. Por eso lo dejamos en `app/`,
 * que es además donde viven sus dependencias.
 *
 * @param {object} permissions Resultado de `usePermissions()`.
 * @returns {string|null} module id seguro o `null` si no hay ninguno accesible.
 */
import { ROLE_HOME } from '../permissions/matrix.js';
import { MODULE_REGISTRY } from './moduleRegistry.js';
import { TENANT_NAV, VIEWER_NAV } from './nav.js';

/**
 * Comprueba si un module id es accesible para un set de permisos.
 * Reglas:
 *  - module id sin entrada en `MODULE_REGISTRY` → no cuenta (no podemos
 *    garantizar que el render no falle).
 *  - entrada con `capability: null` → SIEMPRE accesible (ej. `tenant-setup`).
 *  - entrada con capability → `permissions.can(capability, mode || 'R')`.
 */
function isModuleAccessible(moduleId, permissions) {
  const entry = MODULE_REGISTRY[moduleId];
  if (!entry) return false;
  const { capability, mode = 'R' } = entry;
  if (!capability) return true;
  return permissions.can(capability, mode);
}

/**
 * Devuelve la lista plana de module ids del nav apropiado al rol.
 * Para `viewer` usamos `VIEWER_NAV`; para todos los demás `TENANT_NAV`.
 * `platform_owner` no pasa por este helper — el router lo redirige a
 * `/platform` antes de evaluar el home tenant-scoped.
 */
function flatNavOrder(role) {
  const nav = role === 'viewer' ? VIEWER_NAV : TENANT_NAV;
  return nav.flatMap((section) => section.items);
}

export function resolveSafeHomeModule(permissions) {
  if (!permissions || typeof permissions.can !== 'function') return null;
  const role = permissions.role;

  // BUG-011: el resultado se navega bajo `/t/{slug}/{moduleId}` (TenantHomeRedirect)
  // o `/t/{slug}/read/{moduleId}` (viewer). Si `preferredHome` apunta a un módulo
  // PLATFORM (ej. `ROLE_HOME.platform_owner = 'platform-fleet'`), el router NO
  // tiene route bajo `/t/:tenantSlug/platform-fleet` y cae en `*` (NotFound) =
  // "Esta página no existe". Esto pasa real cuando un platform_owner activa
  // support_mode y entra al workspace de un tenant — sin el filtro abajo, el
  // home post-redirect es una pantalla 404.
  // Solución: solo aceptar `preferredHome` si está en `flatNavOrder(role)` (la
  // misma fuente que usa el sidebar tenant). Sino, fallthrough a step 2.
  const navOrder = flatNavOrder(role);
  const navOrderSet = new Set(navOrder);

  // Step 1: preferred home (ROLE_HOME[role]) — accesible Y tenant-routable.
  // Si la role-table no tiene entry para el rol (caso edge: rol desconocido),
  // `preferredHome` queda `undefined` y caemos directo al nav.
  const preferredHome = ROLE_HOME[role];
  if (
    preferredHome
    && navOrderSet.has(preferredHome)
    && isModuleAccessible(preferredHome, permissions)
  ) {
    return preferredHome;
  }

  // Step 2: primer módulo accesible en el orden visual del nav.
  for (const moduleId of navOrder) {
    if (isModuleAccessible(moduleId, permissions)) {
      return moduleId;
    }
  }

  // Step 3: nada accesible → fallback al StateScreen.
  return null;
}
