/**
 * GdLanding — pantalla de bienvenida del módulo GD.
 *
 * Es la vista por defecto cuando el usuario abre el módulo sin tener
 * una landing específica por rol asignada. Muestra atajos a las áreas
 * del módulo visibles para sus roles.
 */
import React from 'react';

import { gdCanAny, gdLandingFor } from '../../../permissions/gd-matrix.js';

const ATAJOS = Object.freeze([
  { perm: 'VU-001', label: 'Nuevo radicado de entrada', path: '/gd/ventanilla/nuevo-entrada' },
  { perm: 'PQRSD-009', label: 'Mis PQRSD pendientes', path: '/gd/pqrsd/mias' },
  { perm: 'FIR-001', label: 'Documentos por firmar', path: '/gd/firmas/por-firmar' },
  { perm: 'CI-001', label: 'Nueva correspondencia interna', path: '/gd/correspondencia/interna/nueva' },
  { perm: 'TRD-001', label: 'Editor TRD', path: '/gd/trd' },
  { perm: 'AUD-001', label: 'Consulta de auditoría', path: '/gd/auditoria' },
  { perm: 'USR-001', label: 'Gestión de usuarios', path: '/gd/admin/usuarios' },
  { perm: 'PER-001', label: 'Periféricos autorizados', path: '/gd/admin/perifericos' },
]);

export function GdLanding({ roles = [], onNavigate, user }) {
  const visibles = ATAJOS.filter((a) => gdCanAny(roles, a.perm, 'R'));
  const target = gdLandingFor(roles);

  return (
    <div data-testid="gd-landing">
      <div className="page-head">
        <div className="title-block">
          <h1>Gestión Documental</h1>
          <p className="subtitle">
            {user?.nombre ? `Bienvenido, ${user.nombre}. ` : 'Bienvenido. '}
            Seleccione una opción para continuar.
          </p>
        </div>
        {target !== '/gd' && (
          <div className="actions">
            <button
              type="button"
              className="btn btn-accent"
              onClick={() => onNavigate?.(target)}
            >
              Ir a mi área de trabajo
            </button>
          </div>
        )}
      </div>

      {visibles.length === 0 ? (
        <div className="empty">
          <p>
            No tiene permisos activos en el módulo de Gestión Documental.
            Solicite a su administrador la activación de su perfil.
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 'var(--s-4)',
          }}
        >
          {visibles.map((a) => (
            <button
              key={a.perm}
              type="button"
              className="card"
              data-testid={`gd-atajo-${a.perm}`}
              style={{
                textAlign: 'left',
                padding: 'var(--s-4)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-default)',
                cursor: 'pointer',
              }}
              onClick={() => onNavigate?.(a.path)}
            >
              <div style={{ fontWeight: 600, fontSize: 14 }}>{a.label}</div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {a.path}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default GdLanding;
