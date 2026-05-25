/**
 * GdSidebar — navegación lateral del módulo Gestión Documental.
 *
 * Arma el árbol de navegación a partir del rol GD del usuario.
 * Items ocultos si el rol no tiene NINGÚN permiso UI listado en `requires`.
 *
 * Mapa derivado de UI_BACKLOG.md sección 3 (rol → landing + sidebar visible)
 * + MATRIZ_PERMISOS.md.
 *
 * URLs (esquema D-ROUTES-01):
 *   - Operación: `/gd/t/{slug}/{subPath}`
 *   - Admin del módulo: `/gd/admin/t/{slug}/{subPath}`
 * El sidebar declara `subPath` relativo al módulo (`/buzon`,
 * `/admin/usuarios`); `gdHome(slug, subPath)` construye la URL final
 * y auto-promueve `/admin/...` al sub-tree de admin.
 */
import React from 'react';

import { gdCanAny } from '../../../permissions/gd-matrix.js';
import { gdHome } from '../../../app/urls.js';
import { gdPrimaryRoleLabel } from './gdRoles.js';

const NAV = Object.freeze([
  {
    label: 'OPERACIÓN',
    items: [
      { id: 'ventanilla', label: 'Ventanilla Única', subPath: '/ventanilla', requires: ['VU-001', 'VU-002', 'VU-005'] },
      { id: 'cola-vu', label: 'Cola Ventanilla', subPath: '/ventanilla/cola', requires: ['VU-005', 'VU-006'] },
      { id: 'buzon', label: 'Mi buzón', subPath: '/buzon', requires: ['PQRSD-009', 'PQRSD-READ', 'DOC-002', 'CI-002'] },
      { id: 'buzon-dep', label: 'Buzón de dependencia', subPath: '/buzon/dependencia', requires: ['PQRSD-008', 'USR-009'] },
      { id: 'por-firmar', label: 'Por firmar', subPath: '/firmas/por-firmar', requires: ['FIR-001'] },
    ],
  },
  {
    label: 'PQRSD',
    items: [
      { id: 'pqrsd-panel', label: 'Panel PQRSD', subPath: '/pqrsd', requires: ['PQRSD-006', 'PQRSD-007'] },
      { id: 'pqrsd-mias', label: 'Mis PQRSD', subPath: '/pqrsd/mias', requires: ['PQRSD-009'] },
      { id: 'pqrsd-vencimientos', label: 'Vencimientos', subPath: '/pqrsd/vencimientos', requires: ['PQRSD-006', 'PQRSD-READ'] },
    ],
  },
  {
    label: 'CORRESPONDENCIA',
    items: [
      { id: 'corresp-interna', label: 'Interna', subPath: '/correspondencia/interna', requires: ['CI-001', 'CI-002'] },
      { id: 'corresp-externa', label: 'Externa', subPath: '/correspondencia/externa', requires: ['CE-001', 'CE-005', 'CE-006'] },
    ],
  },
  {
    label: 'DOCUMENTOS',
    items: [
      { id: 'biblioteca', label: 'Biblioteca', subPath: '/documentos', requires: ['DOC-002'] },
      { id: 'plantillas', label: 'Plantillas', subPath: '/plantillas', requires: ['PLA-001', 'PLA-USE'] },
    ],
  },
  {
    label: 'CLASIFICACIÓN',
    items: [
      { id: 'trd', label: 'TRD / TVD', subPath: '/trd', requires: ['TRD-001', 'TRD-READ'] },
      { id: 'expedientes', label: 'Expedientes', subPath: '/expedientes', requires: ['EXP-READ'] },
    ],
  },
  {
    label: 'AUDITORÍA',
    items: [
      { id: 'auditoria', label: 'Eventos', subPath: '/auditoria', requires: ['AUD-001'] },
      { id: 'reportes', label: 'Reportes', subPath: '/reportes', requires: ['REP-001'] },
    ],
  },
  {
    label: 'ADMIN',
    items: [
      // `/admin/...` se auto-promueve a `/gd/admin/t/{slug}/...` via gdHome.
      { id: 'admin-usuarios', label: 'Usuarios', subPath: '/admin/usuarios', requires: ['USR-001', 'USR-010'] },
      { id: 'admin-estructura', label: 'Estructura orgánica', subPath: '/admin/estructura', requires: ['USR-001'] },
      { id: 'admin-catalogos', label: 'Catálogos', subPath: '/admin/catalogos', requires: ['USR-001'] },
      { id: 'admin-parametros', label: 'Parámetros', subPath: '/admin/parametros', requires: ['USR-001'] },
      { id: 'admin-perifericos', label: 'Periféricos', subPath: '/admin/perifericos', requires: ['PER-001'] },
      { id: 'seguridad', label: 'Seguridad', subPath: '/seguridad', requires: ['SEG-PWD', 'SEG-SES'] },
    ],
  },
]);

/**
 * Construye la URL final para un item del nav. Si no hay `tenantSlug`
 * (tests aislados) devuelve el subPath crudo — la navegación no funcionará
 * pero el render no rompe.
 */
function itemHref(tenantSlug, subPath) {
  if (!tenantSlug) return subPath;
  return gdHome(tenantSlug, subPath);
}

export function GdSidebar({
  roles = [],
  tenantSlug,
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
            {/* Rol mostrado: el "más fuerte" del usuario (`gdRolePrimary`)
                con label humano (`gdRoleLabel`). Antes: "GD.ADMIN_SISTEMA"
                — ilegible para usuarios no técnicos. Ahora: "Administrador
                del sistema". Si tiene varios roles, prevalece el admin. */}
            <div className="rol" title={roles.join(', ')}>{gdPrimaryRoleLabel(roles)}</div>
          </div>
        </div>
      )}

      <nav className="sidebar-nav" data-testid="gd-sidebar-nav">
        {groups.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((it) => {
              const href = itemHref(tenantSlug, it.subPath);
              const active = currentPath === href
                || currentPath.startsWith(`${href}/`);
              return (
                <a
                  key={it.id}
                  href={href}
                  className={`nav-link ${active ? 'active' : ''}`}
                  onClick={(e) => {
                    if (onNavigate) {
                      e.preventDefault();
                      onNavigate(href, it.id);
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
