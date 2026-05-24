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
import { useGdScope } from '../hooks/useGdScope.js';
import '../styles/portal.css';

export function GdShell({
  user,
  roles = [],
  tenantSlug,
  currentPath = '',
  breadcrumbs = [],
  onNavigate,
  unreadNotifications = 0,
  onOpenNotifications,
  children,
}) {
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
