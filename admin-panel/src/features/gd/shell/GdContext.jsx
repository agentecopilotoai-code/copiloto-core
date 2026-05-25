/**
 * GdContext — provee identidad + roles del usuario actual a TODOS los
 * componentes del módulo GD sin necesidad de drilling props.
 *
 * Antes (drilling): cada componente de página declaraba
 *   ({ session, roles = [], ...shellProps })
 * y debía recordar pasar `roles={roles}` a <GdShell>. 50+ componentes,
 * fácil olvido → GdShell ve `roles=[]` (default) → sidebar muestra "sin rol"
 * Y el sidebar se renderiza sin opciones (todos los items requieren
 * permisos).
 *
 * Después (context): el `GdProfileLoader` (router) envuelve TODO el módulo
 * en <GdProvider value={{user, roles, session, ...}}>. Cualquier
 * componente hijo (GdShell, GdSidebar, páginas) lee del context vía
 * `useGdContext()`. Si un componente sigue recibiendo `roles` por prop,
 * gana la prop (compat backward) — el context es fallback.
 *
 * Esto elimina la clase de bug "el menú se borra al navegar" de raíz.
 */
import React, { createContext, useContext, useMemo } from 'react';


const GdContextInstance = createContext({
  user: null,
  roles: [],
  session: null,
  tenantSlug: null,
  activeTenantId: null,
});

/**
 * Provider — montar UNA SOLA VEZ alto en el árbol del módulo
 * (típicamente en GdProfileLoader del router). Children acceden via
 * `useGdContext()`.
 */
export function GdProvider({
  user = null,
  roles = [],
  session = null,
  tenantSlug = null,
  activeTenantId = null,
  children,
}) {
  // useMemo evita re-renders innecesarios cuando los hijos consumen el
  // objeto entero — sin esto, cualquier render del padre crea un objeto
  // nuevo y todos los consumidores se invalidan.
  const value = useMemo(
    () => ({ user, roles, session, tenantSlug, activeTenantId }),
    [user, roles, session, tenantSlug, activeTenantId],
  );
  return (
    <GdContextInstance.Provider value={value}>
      {children}
    </GdContextInstance.Provider>
  );
}

/**
 * Hook de acceso al contexto. Devuelve siempre el objeto default si no
 * hay provider (no rompe en tests aislados que renderizan un componente
 * fuera del módulo). Para casos donde el provider es REQUERIDO, el
 * componente debe validar `if (!ctx.session)` y mostrar fallback.
 */
export function useGdContext() {
  return useContext(GdContextInstance);
}
