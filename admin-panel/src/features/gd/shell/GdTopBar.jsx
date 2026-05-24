/**
 * GdTopBar — barra superior del módulo GD.
 *
 * Elementos:
 *  - Buscador global (RNF-039) — `/gd/buscar?q=...`. Atajo Cmd/Ctrl+K.
 *  - ScopeSelector (UI_BACKLOG §1 mandato 6).
 *  - Notificaciones (badge si hay) — wire en bloque UI-13.
 *  - User chip — nombre + avatar + dropdown logout (en bloques posteriores).
 */
import React, { useEffect, useRef } from 'react';

import { GD_SCOPE_LABELS } from '../hooks/useGdScope.js';

export function GdTopBar({
  scope = 'propio',
  scopes = ['propio', 'dependencias_autorizadas', 'institucional'],
  onScopeChange,
  onSearch,
  searchValue = '',
  user,
  unreadNotifications = 0,
  onOpenNotifications,
}) {
  const searchRef = useRef(null);

  useEffect(() => {
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleKey);
      return () => window.removeEventListener('keydown', handleKey);
    }
    return undefined;
  }, []);

  return (
    <header className="topbar" data-testid="gd-topbar">
      <div className="search">
        <span aria-hidden="true">🔍</span>
        <input
          ref={searchRef}
          type="search"
          placeholder="Buscar radicado, PQRSD, documento…"
          value={searchValue}
          onChange={(e) => onSearch?.(e.target.value)}
          aria-label="Búsqueda global"
          data-testid="gd-search"
        />
        <span className="shortcut" aria-hidden="true">⌘K</span>
      </div>

      <div className="spacer" />

      <div className="scope" data-testid="gd-scope-selector">
        <span className="label">Alcance:</span>
        <select
          value={scope}
          onChange={(e) => onScopeChange?.(e.target.value)}
          className="select"
          style={{
            height: 28, padding: '0 24px 0 8px',
            background: 'transparent', border: 'none',
            fontWeight: 600, fontSize: 12.5,
            color: 'var(--fg-primary)',
          }}
          aria-label="Cambiar alcance"
        >
          {scopes.map((s) => (
            <option key={s} value={s}>{GD_SCOPE_LABELS[s] || s}</option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className="icon-btn"
        aria-label="Notificaciones"
        onClick={onOpenNotifications}
        data-testid="gd-notifications-btn"
      >
        🔔
        {unreadNotifications > 0 && <span className="dot" aria-hidden="true" />}
      </button>

      {user && (
        <button type="button" className="user-chip" aria-label="Cuenta del usuario">
          <span className="avatar" aria-hidden="true">
            {(user.nombre || '?').slice(0, 1).toUpperCase()}
          </span>
          <span className="name">{user.nombre || 'Usuario'}</span>
        </button>
      )}
    </header>
  );
}

export default GdTopBar;
