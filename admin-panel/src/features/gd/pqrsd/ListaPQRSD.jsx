/**
 * ListaPQRSD — GD-UI-0021. DataTable con semáforo de vencimiento.
 *
 * Filtros: estado, tipo, dependencia, vencimiento (vigente|proximo|vencido).
 * Cada fila integra `TerminoVencimientoBadge` con `dias_restantes` y
 * `termino_dias` calculados en el backend (GD-API-0042).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { PQRSDStatusChip } from '../components/PQRSDStatusChip.jsx';
import { TerminoVencimientoBadge } from '../components/TerminoVencimientoBadge.jsx';
import { usePQRSDList } from './useGdPQRSD.js';
import { useGdScope } from '../hooks/useGdScope.js';

const ESTADOS = [
  '', 'nueva', 'asignada', 'en_proyeccion', 'en_revision',
  'aprobada', 'firmada', 'cerrada', 'anulada',
];
const VTOS = [
  { value: '', label: 'Todos' },
  { value: 'vigente', label: 'Vigentes' },
  { value: 'proximo', label: 'Próximos a vencer' },
  { value: 'vencido', label: 'Vencidos' },
];

export function ListaPQRSD({
  session,
  tenantSlug,
  dependencias = [],
  onNavigate,
  titulo = 'PQRSD',
  filtrosIniciales = {},
  ...shellProps
}) {
  const { scope } = useGdScope(tenantSlug);
  const [filtros, setFiltros] = useState(filtrosIniciales);
  const { items, total, loading, error, refresh } =
    usePQRSDList(session, { ...filtros, scope });

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <GdShell
      {...shellProps}
      tenantSlug={tenantSlug}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: titulo },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>{titulo}</h1>
          <p className="subtitle">
            {total} registro(s). Alcance actual: <strong>{scope}</strong>.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="lista-refresh"
          >
            Actualizar
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--s-3)',
          }}
        >
          <div className="field">
            <label>Estado</label>
            <select
              className="select"
              value={filtros.estado || ''}
              onChange={(e) => update('estado', e.target.value)}
              data-testid="lista-filter-estado"
            >
              {ESTADOS.map((e) => (
                <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Tipo</label>
            <select
              className="select"
              value={filtros.tipo || ''}
              onChange={(e) => update('tipo', e.target.value)}
              data-testid="lista-filter-tipo"
            >
              <option value="">Todos</option>
              <option value="P">Petición</option>
              <option value="Q">Queja</option>
              <option value="R">Reclamo</option>
              <option value="S">Sugerencia</option>
              <option value="D">Denuncia</option>
            </select>
          </div>
          <div className="field">
            <label>Vencimiento</label>
            <select
              className="select"
              value={filtros.vencimiento || ''}
              onChange={(e) => update('vencimiento', e.target.value)}
              data-testid="lista-filter-vto"
            >
              {VTOS.map((v) => (
                <option key={v.value} value={v.value}>{v.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Dependencia</label>
            <select
              className="select"
              value={filtros.dependencia_id || ''}
              onChange={(e) => update('dependencia_id', e.target.value)}
              data-testid="lista-filter-dep"
            >
              <option value="">Todas</option>
              {dependencias.map((d) => (
                <option key={d.id} value={d.id}>{d.nombre}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="lista-empty" style={{ margin: 'var(--s-4)' }}>
            <p>No hay PQRSD con esos filtros.</p>
          </div>
        )}
        {items.length > 0 && (
          <table className="data-table" data-testid="lista-table">
            <thead>
              <tr>
                <th>Número</th>
                <th>Tipo</th>
                <th>Estado</th>
                <th>Asunto</th>
                <th>Dependencia</th>
                <th>Vencimiento</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr
                  key={p.id}
                  data-testid="lista-row"
                  onClick={() => onNavigate?.(`/gd/pqrsd/${p.id}`)}
                >
                  <td className="num">{p.numero_radicado}</td>
                  <td><PQRSDStatusChip tipo={p.tipo} withLabel={false} /></td>
                  <td>
                    <span className={`badge ${badgeTone(p.estado)}`}>{p.estado}</span>
                  </td>
                  <td>{p.asunto}</td>
                  <td>{p.dependencia_actual_nombre || '—'}</td>
                  <td style={{ minWidth: 150 }}>
                    {Number.isFinite(p.dias_restantes) && (
                      <TerminoVencimientoBadge
                        diasRestantes={p.dias_restantes}
                        terminoTotal={p.termino_dias}
                        compact
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </GdShell>
  );
}

function badgeTone(estado) {
  if (estado === 'cerrada' || estado === 'aprobada' || estado === 'firmada') return 'ok';
  if (estado === 'anulada' || estado === 'vencida') return 'danger';
  if (estado === 'en_proyeccion' || estado === 'en_revision' || estado === 'asignada') return 'info';
  return 'neutral';
}

export default ListaPQRSD;
