/**
 * GdSidebar — navegación lateral del módulo Gestión Documental.
 *
 * Arma el árbol de navegación a partir del rol GD del usuario.
 * Items ocultos si el rol no tiene NINGÚN permiso UI listado en `requires`.
 *
 * Mapa derivado de UI_BACKLOG.md sección 3 (rol → landing + sidebar visible)
 * + MATRIZ_PERMISOS.md.
 */
import React from 'react';

import { gdCanAny } from '../../../permissions/gd-matrix.js';

const NAV = Object.freeze([
  {
    label: 'OPERACIÓN',
    items: [
      { id: 'ventanilla', label: 'Ventanilla Única', path: '/gd/ventanilla', requires: ['VU-001', 'VU-002', 'VU-005'] },
      { id: 'cola-vu', label: 'Cola Ventanilla', path: '/gd/ventanilla/cola', requires: ['VU-005', 'VU-006'] },
      { id: 'buzon', label: 'Mi buzón', path: '/gd/buzon', requires: ['PQRSD-009', 'PQRSD-READ', 'DOC-002', 'CI-002'] },
      { id: 'buzon-dep', label: 'Buzón de dependencia', path: '/gd/buzon/dependencia', requires: ['PQRSD-008', 'USR-009'] },
      { id: 'por-firmar', label: 'Por firmar', path: '/gd/firmas/por-firmar', requires: ['FIR-001'] },
    ],
  },
  {
    label: 'PQRSD',
    items: [
      { id: 'pqrsd-panel', label: 'Panel PQRSD', path: '/gd/pqrsd', requires: ['PQRSD-006', 'PQRSD-007'] },
      { id: 'pqrsd-mias', label: 'Mis PQRSD', path: '/gd/pqrsd/mias', requires: ['PQRSD-009'] },
      { id: 'pqrsd-vencimientos', label: 'Vencimientos', path: '/gd/pqrsd/vencimientos', requires: ['PQRSD-006', 'PQRSD-READ'] },
    ],
  },
  {
    label: 'CORRESPONDENCIA',
    items: [
      { id: 'corresp-interna', label: 'Interna', path: '/gd/correspondencia/interna', requires: ['CI-001', 'CI-002'] },
      { id: 'corresp-externa', label: 'Externa', path: '/gd/correspondencia/externa', requires: ['CE-001', 'CE-005', 'CE-006'] },
    ],
  },
  {
    label: 'DOCUMENTOS',
    items: [
      { id: 'biblioteca', label: 'Biblioteca', path: '/gd/documentos', requires: ['DOC-002'] },
      { id: 'plantillas', label: 'Plantillas', path: '/gd/plantillas', requires: ['PLA-001', 'PLA-USE'] },
    ],
  },
  {
    label: 'CLASIFICACIÓN',
    items: [
      { id: 'trd', label: 'TRD / TVD', path: '/gd/trd', requires: ['TRD-001', 'TRD-READ'] },
      { id: 'expedientes', label: 'Expedientes', path: '/gd/expedientes', requires: ['EXP-READ'] },
    ],
  },
  {
    label: 'AUDITORÍA',
    items: [
      { id: 'auditoria', label: 'Eventos', path: '/gd/auditoria', requires: ['AUD-001'] },
      { id: 'reportes', label: 'Reportes', path: '/gd/reportes', requires: ['REP-001'] },
    ],
  },
  {
    label: 'ADMIN',
    items: [
      { id: 'admin-usuarios', label: 'Usuarios', path: '/gd/admin/usuarios', requires: ['USR-001', 'USR-010'] },
      { id: 'admin-estructura', label: 'Estructura orgánica', path: '/gd/admin/estructura', requires: ['USR-001'] },
      { id: 'admin-catalogos', label: 'Catálogos', path: '/gd/admin/catalogos', requires: ['USR-001'] },
      { id: 'admin-parametros', label: 'Parámetros', path: '/gd/admin/parametros', requires: ['USR-001'] },
      { id: 'admin-perifericos', label: 'Periféricos', path: '/gd/admin/perifericos', requires: ['PER-001'] },
      { id: 'seguridad', label: 'Seguridad', path: '/gd/seguridad', requires: ['SEG-PWD', 'SEG-SES'] },
    ],
  },
]);

export function GdSidebar({
  roles = [],
  currentPath = '',
  onNavigate,
  user,
  brandTitle = 'Gestión Documental',
  brandSubtitle = 'Estado · 2026',
}) {
  const groups = NAV.map((group) => {
    const visible = group.items.filter((it) =>
      it.requires.some((p) => gdCanAny(roles, p, 'R')),
    );
    return { ...group, items: visible };
  }).filter((g) => g.items.length > 0);

  return (
    <aside className="sidebar" aria-label="Navegación Gestión Documental">
      <div className="sidebar-brand">
        <div className="mark" aria-hidden="true">GD</div>
        <div>
          <div className="title">{brandTitle}</div>
          <div className="subtitle">{brandSubtitle}</div>
        </div>
      </div>

      {user && (
        <div className="sidebar-role">
          <div className="avatar" aria-hidden="true">
            {(user.nombre || '?').slice(0, 1).toUpperCase()}
          </div>
          <div>
            <div className="name">{user.nombre || 'Usuario'}</div>
            <div className="rol">{(roles[0] || 'sin rol').replace('gd.', '').toUpperCase()}</div>
          </div>
        </div>
      )}

      <nav className="sidebar-nav" data-testid="gd-sidebar-nav">
        {groups.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((it) => {
              const active = currentPath === it.path
                || currentPath.startsWith(`${it.path}/`);
              return (
                <a
                  key={it.id}
                  href={it.path}
                  className={`nav-link ${active ? 'active' : ''}`}
                  onClick={(e) => {
                    if (onNavigate) {
                      e.preventDefault();
                      onNavigate(it.path, it.id);
                    }
                  }}
                  data-nav-id={it.id}
                >
                  <span>{it.label}</span>
                </a>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        <span>v0.1 GD</span>
        <span>©2026</span>
      </div>
    </aside>
  );
}

export const _NAV_FOR_TEST = NAV;
export default GdSidebar;
