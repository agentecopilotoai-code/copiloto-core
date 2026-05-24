/**
 * BuscarRadicados — GD-UI-0013. Búsqueda global de radicados.
 *
 * Filtros: número, tercero, asunto, estado, fecha desde/hasta, dependencia,
 * serie, vencimiento, canal. Respeta el alcance del usuario (RNF-039/021),
 * pasado al backend como query param `scope`.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useBuscarRadicados } from './useGdRadicados.js';
import { useGdScope } from '../hooks/useGdScope.js';

export function BuscarRadicados({
  session,
  tenantSlug,
  canales = [],
  estados = ['radicado', 'en_gestion', 'cerrado', 'anulado'],
  dependencias = [],
  onNavigate,
  ...shellProps
}) {
  const { scope } = useGdScope(tenantSlug);
  const [filtros, setFiltros] = useState({});
  const [submitted, setSubmitted] = useState(false);

  const { items, total, loading, error, refresh } =
    useBuscarRadicados(session, { ...filtros, scope }, { enabled: submitted });

  function update(k, v) {
    setFiltros((p) => ({ ...p, [k]: v || undefined }));
  }

  function handleBuscar() {
    setSubmitted(true);
    refresh();
  }

  function handleLimpiar() {
    setFiltros({});
    setSubmitted(false);
  }

  return (
    <GdShell
      {...shellProps}
      tenantSlug={tenantSlug}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Búsqueda' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Búsqueda global</h1>
          <p className="subtitle">
            Consulta avanzada de radicados. Alcance actual: <strong>{scope}</strong>.
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-5)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 'var(--s-3)',
          }}
          data-testid="buscar-filtros"
        >
          <FilterField label="Número de radicado">
            <input
              className="input"
              value={filtros.numero || ''}
              onChange={(e) => update('numero', e.target.value)}
              data-testid="filter-numero"
            />
          </FilterField>
          <FilterField label="Tercero (nombre o doc)">
            <input
              className="input"
              value={filtros.tercero || ''}
              onChange={(e) => update('tercero', e.target.value)}
              data-testid="filter-tercero"
            />
          </FilterField>
          <FilterField label="Asunto contiene">
            <input
              className="input"
              value={filtros.asunto || ''}
              onChange={(e) => update('asunto', e.target.value)}
              data-testid="filter-asunto"
            />
          </FilterField>
          <FilterField label="Estado">
            <select
              className="select"
              value={filtros.estado || ''}
              onChange={(e) => update('estado', e.target.value)}
              data-testid="filter-estado"
            >
              <option value="">Cualquiera</option>
              {estados.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </FilterField>
          <FilterField label="Canal">
            <select
              className="select"
              value={filtros.canal_id || ''}
              onChange={(e) => update('canal_id', e.target.value)}
              data-testid="filter-canal"
            >
              <option value="">Cualquiera</option>
              {canales.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          </FilterField>
          <FilterField label="Dependencia">
            <select
              className="select"
              value={filtros.dependencia || ''}
              onChange={(e) => update('dependencia', e.target.value)}
              data-testid="filter-dep"
            >
              <option value="">Cualquiera</option>
              {dependencias.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
            </select>
          </FilterField>
          <FilterField label="Fecha desde">
            <input
              type="date"
              className="input"
              value={filtros.fecha_desde || ''}
              onChange={(e) => update('fecha_desde', e.target.value)}
              data-testid="filter-desde"
            />
          </FilterField>
          <FilterField label="Fecha hasta">
            <input
              type="date"
              className="input"
              value={filtros.fecha_hasta || ''}
              onChange={(e) => update('fecha_hasta', e.target.value)}
              data-testid="filter-hasta"
            />
          </FilterField>
          <FilterField label="Vencimiento">
            <select
              className="select"
              value={filtros.vencimiento || ''}
              onChange={(e) => update('vencimiento', e.target.value)}
              data-testid="filter-vto"
            >
              <option value="">Cualquiera</option>
              <option value="vigente">Vigente</option>
              <option value="proximo">Próximo a vencer</option>
              <option value="vencido">Vencido</option>
            </select>
          </FilterField>
          <FilterField label="Serie documental">
            <input
              className="input"
              value={filtros.serie || ''}
              onChange={(e) => update('serie', e.target.value)}
              data-testid="filter-serie"
            />
          </FilterField>
        </div>
        <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
          <button
            type="button"
            className="btn btn-accent"
            onClick={handleBuscar}
            data-testid="buscar-submit"
          >
            Buscar
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleLimpiar}
            data-testid="buscar-limpiar"
          >
            Limpiar
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {!submitted && (
          <div className="empty" style={{ margin: 'var(--s-4)' }}>
            <p className="muted">
              Aplique filtros y presione <strong>Buscar</strong> para
              consultar.
            </p>
          </div>
        )}
        {submitted && loading && (
          <p className="muted" style={{ padding: 'var(--s-4)' }}>Buscando…</p>
        )}
        {submitted && error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        {submitted && !loading && !error && items.length === 0 && (
          <div className="empty" data-testid="buscar-vacio" style={{ margin: 'var(--s-4)' }}>
            <p>No se encontraron radicados con esos criterios.</p>
          </div>
        )}
        {submitted && items.length > 0 && (
          <>
            <div className="table-toolbar" style={{ justifyContent: 'space-between' }}>
              <span className="muted">
                {total} radicado(s) encontrado(s).
              </span>
            </div>
            <table className="data-table" data-testid="buscar-table">
              <thead>
                <tr>
                  <th>Número</th>
                  <th>Fecha</th>
                  <th>Estado</th>
                  <th>Asunto</th>
                  <th>Dependencia</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    data-testid="buscar-row"
                    onClick={() => onNavigate?.(`/gd/ventanilla/radicados/${r.id}`)}
                  >
                    <td className="num">{r.numero_radicado}</td>
                    <td>{fmtFecha(r.fecha_radicacion)}</td>
                    <td>
                      <span className={`badge ${badgeTone(r.estado)}`}>
                        {r.estado}
                      </span>
                    </td>
                    <td>{r.asunto}</td>
                    <td>{r.dependencia_actual_nombre || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </GdShell>
  );
}

function FilterField({ label, children }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}

function badgeTone(estado) {
  if (estado === 'cerrado' || estado === 'aprobado') return 'ok';
  if (estado === 'anulado' || estado === 'vencido') return 'danger';
  if (estado === 'en_gestion' || estado === 'en_revision') return 'info';
  return 'neutral';
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch { return iso; }
}

export default BuscarRadicados;
