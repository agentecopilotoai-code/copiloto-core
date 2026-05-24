/**
 * VentanillaHome — landing del módulo Ventanilla Única (GD-UI-EP-002).
 *
 * Es la primera vista al entrar al sub-módulo. Muestra accesos rápidos
 * a las acciones más comunes (nuevo entrada/salida/cola) y KPIs básicos
 * que vienen del backend cuando estén disponibles.
 */
import React from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const ACCIONES = Object.freeze([
  {
    id: 'nuevo-entrada',
    label: 'Nuevo radicado de entrada',
    desc: 'Registrar un documento recibido del exterior.',
    path: '/gd/ventanilla/nuevo-entrada',
    perm: 'VU-001',
  },
  {
    id: 'nuevo-salida',
    label: 'Nuevo radicado de salida',
    desc: 'Radicar un oficio emitido por la entidad.',
    path: '/gd/ventanilla/nuevo-salida',
    perm: 'VU-002',
  },
  {
    id: 'cola',
    label: 'Cola de clasificación',
    desc: 'Clasificar radicados pendientes.',
    path: '/gd/ventanilla/cola',
    perm: 'VU-005',
  },
  {
    id: 'buscar',
    label: 'Buscar radicados',
    desc: 'Consulta global con filtros avanzados.',
    path: '/gd/ventanilla/buscar',
    perm: 'VU-001',
  },
]);

export function VentanillaHome({
  roles = [],
  kpis,
  onNavigate,
  ...shellProps
}) {
  const accesibles = ACCIONES.filter((a) => gdCanAny(roles, a.perm, 'R'));

  return (
    <GdShell
      {...shellProps}
      roles={roles}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Ventanilla Única</h1>
          <p className="subtitle">
            Recepción, registro y clasificación de toda la correspondencia
            que entra y sale de la entidad.
          </p>
        </div>
      </div>

      {kpis && (
        <div
          data-testid="vu-kpis"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--s-4)',
            marginBottom: 'var(--s-6)',
          }}
        >
          <Kpi label="Radicados hoy" value={kpis.radicados_hoy ?? '—'} />
          <Kpi label="Pendientes clasif." value={kpis.pendientes_clasificacion ?? '—'} />
          <Kpi label="En cola" value={kpis.en_cola ?? '—'} />
          <Kpi label="Anulaciones (mes)" value={kpis.anulaciones_mes ?? '—'} />
        </div>
      )}

      <div
        data-testid="vu-acciones"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 'var(--s-4)',
        }}
      >
        {accesibles.length === 0 && (
          <div className="empty">
            <p>No tiene permisos para operar Ventanilla.</p>
          </div>
        )}
        {accesibles.map((a) => (
          <button
            key={a.id}
            type="button"
            className="card"
            data-testid={`vu-accion-${a.id}`}
            onClick={() => onNavigate?.(a.path)}
            style={{
              textAlign: 'left',
              padding: 'var(--s-4)',
              border: '1px solid var(--border-default)',
              cursor: 'pointer',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 14 }}>{a.label}</div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              {a.desc}
            </div>
          </button>
        ))}
      </div>
    </GdShell>
  );
}

function Kpi({ label, value }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default VentanillaHome;
