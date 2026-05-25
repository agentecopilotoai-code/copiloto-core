/**
 * GdShell — layout principal del módulo Gestión Documental.
 *
 * Componente raíz que envuelve TODAS las vistas del módulo GD:
 *  - Sidebar (rol-aware, navegación contextual).
 *  - TopBar (búsqueda + scope + notificaciones + user chip).
 *  - Content area con breadcrumbs auto-generados.
 *
 * El estilo del shell se aplica scope-local vía `.gd-shell-root` para no
 * contaminar el resto del admin-panel.
 *
 * Carga `portal.css` una sola vez (side-effect import).
 */
import React, { useState } from 'react';

import { GdSidebar } from './GdSidebar.jsx';
import { GdTopBar } from './GdTopBar.jsx';
import { useGdContext } from './GdContext.jsx';
import { useGdScope } from '../hooks/useGdScope.js';
import { SupportModeBanner } from '../../../components/domain/SupportModeBanner.jsx';
import '../styles/portal.css';

export function GdShell({
  user: userProp,
  roles: rolesProp,
  tenantSlug: tenantSlugProp,
  // `activeTenantId` (UUID) — distinto del `tenantSlug` que solo sirve
  // para componer rutas. SupportModeBanner lo necesita para decidir si
  // el override de support_mode corresponde a ESTE tenant.
  activeTenantId: activeTenantIdProp,
  // Callback opcional que se dispara cuando el user hace "Salir de
  // support mode" desde el banner. Necesario porque sin navegación,
  // el user queda dentro del módulo GD sin permisos (la cookie ya no
  // está, `/api/v1/gd/me` falla). El router pasa `() => navigate('/platform')`.
  onExitSupportMode,
  currentPath = '',
  breadcrumbs = [],
  onNavigate,
  unreadNotifications = 0,
  onOpenNotifications,
  children,
}) {
  // Fallback al context: si el componente padre no pasó props explícitas,
  // tomamos los valores del GdProvider (montado en GdProfileLoader del
  // router). Sin esto, cada componente del módulo tenía que pasar
  // `roles={roles}` manualmente — fácil olvido, causa principal del
  // "menú se borra y aparece SIN ROL" al navegar.
  const ctx = useGdContext();
  const user = userProp ?? ctx.user;
  const roles = rolesProp ?? ctx.roles ?? [];
  const tenantSlug = tenantSlugProp ?? ctx.tenantSlug;
  const activeTenantId = activeTenantIdProp ?? ctx.activeTenantId;

  const { scope, setScope, scopes } = useGdScope(tenantSlug);
  const [search, setSearch] = useState('');

  function handleSearch(value) {
    setSearch(value);
  }

  function handleSearchSubmit() {
    if (search.trim()) {
      onNavigate?.(`/gd/buscar?q=${encodeURIComponent(search.trim())}`);
    }
  }

  return (
    <div className="gd-shell-root" data-testid="gd-shell-root" data-scope={scope}>
      <div className="app-shell">
        <GdSidebar
          roles={roles}
          currentPath={currentPath}
          onNavigate={onNavigate}
          user={user}
        />
        <div className="main">
          {/* Mismo banner que `TenantShell` (BUG-008). Sin esto, un
              platform_owner que entra a GD vía support_mode no veía el
              recordatorio + botón "Salir de support mode" y quedaba
              "atrapado" operando con privilegios elevados sin UI para
              salir. El componente se auto-oculta si el override no
              corresponde al `activeTenantId` actual.
              `onExitSupportMode` navega afuera del módulo (sino el user
              ve la página rota: cookie ya no existe, queries 404). */}
          <SupportModeBanner
            activeTenantId={activeTenantId}
            onExited={onExitSupportMode}
          />
          <GdTopBar
            scope={scope}
            scopes={scopes}
            onScopeChange={setScope}
            searchValue={search}
            onSearch={handleSearch}
            onSearchSubmit={handleSearchSubmit}
            user={user}
            unreadNotifications={unreadNotifications}
            onOpenNotifications={onOpenNotifications}
          />
          <main className="content" data-testid="gd-content">
            {breadcrumbs.length > 0 && (
              <nav className="breadcrumb" aria-label="Ruta">
                {breadcrumbs.map((b, i) => {
                  const isLast = i === breadcrumbs.length - 1;
                  return (
                    <span key={`${b.label}-${i}`}>
                      {isLast ? (
                        <span className="here">{b.label}</span>
                      ) : (
                        <>
                          <a
                            href={b.path || '#'}
                            onClick={(e) => {
                              if (b.path && onNavigate) {
                                e.preventDefault();
                                onNavigate(b.path);
                              }
                            }}
                          >
                            {b.label}
                          </a>
                          <span aria-hidden="true"> / </span>
                        </>
                      )}
                    </span>
                  );
                })}
              </nav>
            )}
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

export default GdShell;
