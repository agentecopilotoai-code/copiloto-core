/**
 * ColaVentanilla — GD-UI-0009.
 *
 * DataTable de radicados pendientes de clasificación. Acción "Clasificar"
 * abre un drawer lateral con el paso 4 del wizard (selector de tipo +
 * sub-tipo + justificación opcional).
 *
 * Rol: ROL-004 ve su propia cola (scope='propio'); ROL-005 ve toda la VU
 * (scope='institucional').
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useColaPendientesClasificacion,
  useClasificarRadicado,
} from './useGdRadicados.js';

const TIPOS = [
  { value: 'pqrsd', label: 'PQRSD' },
  { value: 'correspondencia_externa', label: 'Correspondencia externa' },
  { value: 'tramite', label: 'Trámite' },
  { value: 'expediente', label: 'Expediente' },
];

export function ColaVentanilla({ session, onNavigate, ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, total, loading, error, refresh } =
    useColaPendientesClasificacion(session, filtros);
  const [drawerRadicado, setDrawerRadicado] = useState(null);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Cola de clasificación' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Cola de clasificación</h1>
          <p className="subtitle">
            Radicados pendientes de clasificar para ser derivados a la
            dependencia correspondiente. Total: <strong>{total}</strong>.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="cola-refresh"
          >
            Actualizar
          </button>
          <button
            type="button"
            className="btn btn-accent"
            onClick={() => onNavigate?.('/gd/ventanilla/nuevo-entrada')}
          >
            + Nuevo radicado
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="table-toolbar">
          <div className="search-mini">
            <input
              type="search"
              placeholder="Filtrar por asunto…"
              value={filtros.q || ''}
              onChange={(e) => setFiltros({ ...filtros, q: e.target.value })}
              data-testid="cola-filter-q"
            />
          </div>
          <select
            className="select"
            value={filtros.canal_id || ''}
            onChange={(e) => setFiltros({ ...filtros, canal_id: e.target.value || undefined })}
            data-testid="cola-filter-canal"
            style={{ width: 180 }}
          >
            <option value="">Todos los canales</option>
            <option value="web">Web</option>
            <option value="presencial">Presencial</option>
            <option value="correo">Correo</option>
          </select>
        </div>

        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando cola…</p>}

        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
            <div className="body">
              <div className="title">No se pudo cargar la cola.</div>
              <div>{error.message || 'Intente nuevamente.'}</div>
            </div>
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="cola-empty" style={{ margin: 'var(--s-4)' }}>
            <p>No hay radicados pendientes de clasificación en este momento.</p>
          </div>
        )}

        {items.length > 0 && (
          <table className="data-table" data-testid="cola-table">
            <thead>
              <tr>
                <th>Número</th>
                <th>Fecha</th>
                <th>Canal</th>
                <th>Asunto</th>
                <th style={{ textAlign: 'right' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  data-testid="cola-row"
                  onClick={() => onNavigate?.(`/gd/ventanilla/radicados/${r.id}`)}
                >
                  <td className="num">{r.numero_radicado}</td>
                  <td>{fmtFecha(r.fecha_radicacion)}</td>
                  <td>{r.canal_nombre || '—'}</td>
                  <td>{r.asunto}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      className="btn btn-sm btn-accent"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDrawerRadicado(r);
                      }}
                      data-testid="cola-clasificar-btn"
                    >
                      Clasificar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {drawerRadicado && (
        <ClasificarDrawer
          session={session}
          radicado={drawerRadicado}
          onClose={() => setDrawerRadicado(null)}
          onSuccess={() => {
            setDrawerRadicado(null);
            refresh();
          }}
        />
      )}
    </GdShell>
  );
}

function ClasificarDrawer({ session, radicado, onClose, onSuccess }) {
  const [tipo, setTipo] = useState('');
  const [subTipo, setSubTipo] = useState('');
  const [justificacion, setJustificacion] = useState('');
  const { submitting, error, submit } = useClasificarRadicado(session);

  async function handleClasificar() {
    try {
      await submit(radicado.id, {
        tipo_clasificacion: tipo,
        sub_tipo: subTipo || undefined,
        justificacion: justificacion || undefined,
      });
      onSuccess?.();
    } catch {
      /* error en hook */
    }
  }

  return (
    <aside
      data-testid="clasificar-drawer"
      style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 400,
        background: 'white', borderLeft: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-lg)', zIndex: 50,
        display: 'flex', flexDirection: 'column',
      }}
    >
      <header style={{ padding: 'var(--s-4)', borderBottom: '1px solid var(--border-default)' }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Clasificar radicado</h2>
        <div className="muted" style={{ fontSize: 12 }}>{radicado.numero_radicado}</div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onClose}
          style={{ position: 'absolute', top: 8, right: 8 }}
          aria-label="Cerrar"
        >
          ✕
        </button>
      </header>
      <div style={{ padding: 'var(--s-4)', flex: 1, overflow: 'auto' }}>
        <div className="field">
          <label>Tipo de clasificación <span className="req">*</span></label>
          <select
            className="select"
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            data-testid="drawer-tipo"
          >
            <option value="">Seleccione…</option>
            {TIPOS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Sub-tipo (opcional)</label>
          <input
            className="input"
            value={subTipo}
            onChange={(e) => setSubTipo(e.target.value)}
          />
        </div>
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Justificación (opcional)</label>
          <textarea
            className="textarea"
            rows={3}
            value={justificacion}
            onChange={(e) => setJustificacion(e.target.value)}
          />
        </div>
        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">
              <div>{error.message || 'No se pudo clasificar.'}</div>
            </div>
          </div>
        )}
      </div>
      <footer style={{ padding: 'var(--s-4)', borderTop: '1px solid var(--border-default)', display: 'flex', gap: 'var(--s-2)' }}>
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-accent"
          onClick={handleClasificar}
          disabled={!tipo || submitting}
          data-testid="drawer-clasificar-submit"
        >
          {submitting ? 'Clasificando…' : 'Clasificar'}
        </button>
      </footer>
    </aside>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch { return iso; }
}

export default ColaVentanilla;
