/**
 * BuzonDependencia — GD-UI-0017.
 *
 * Misma estructura que MiBuzon pero scope='dependencia'. Vista adicional
 * "Carga del equipo" (tab) — KPIs por usuario (PERM-REP-009).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  CARPETAS,
  useBuzonDependencia,
  useCargaEquipo,
} from './useGdBuzon.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['Buzón', 'Carga del equipo'];

export function BuzonDependencia({
  session,
  roles = [],
  onNavigate,
  ...shellProps
}) {
  const [tab, setTab] = useState('Buzón');
  const [carpeta, setCarpeta] = useState('pqrsd');
  const [selectedId, setSelectedId] = useState(null);

  const { items, contadores, loading, error, refresh } =
    useBuzonDependencia(session, { carpeta });

  const puedeVerCarga = gdCanAny(roles, 'REP-009', 'R');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Buzón dependencia' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Buzón de dependencia</h1>
          <p className="subtitle">
            Vista consolidada del equipo. Las acciones requieren PERM-USR-009.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="dep-refresh"
          >
            Actualizar
          </button>
        </div>
      </div>

      <nav className="tabs" data-testid="dep-tabs" role="tablist">
        {TABS.map((t) => {
          const disabled = t === 'Carga del equipo' && !puedeVerCarga;
          return (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={`tab ${tab === t ? 'active' : ''}`}
              onClick={() => !disabled && setTab(t)}
              data-testid={`dep-tab-${t}`}
              disabled={disabled}
              style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}
              title={disabled ? 'No tiene permiso PERM-REP-009' : undefined}
            >
              {t}
            </button>
          );
        })}
      </nav>

      {tab === 'Buzón' && (
        <BuzonGrid
          carpetas={CARPETAS}
          carpeta={carpeta}
          contadores={contadores}
          items={items}
          loading={loading}
          error={error}
          selectedId={selectedId}
          onChangeCarpeta={(c) => { setCarpeta(c); setSelectedId(null); }}
          onSelect={setSelectedId}
          onNavigate={onNavigate}
        />
      )}
      {tab === 'Carga del equipo' && puedeVerCarga && (
        <CargaEquipoPanel session={session} />
      )}
    </GdShell>
  );
}

function BuzonGrid({
  carpetas, carpeta, contadores, items, loading, error,
  selectedId, onChangeCarpeta, onSelect, onNavigate,
}) {
  const selected = items.find((i) => i.id === selectedId) || items[0];
  return (
    <div
      data-testid="dep-buzon-grid"
      style={{
        display: 'grid',
        gridTemplateColumns: '220px 380px 1fr',
        gap: 0,
        minHeight: 'calc(100vh - 200px)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--r-lg)',
        overflow: 'hidden',
        background: 'var(--bg-surface)',
      }}
    >
      <aside style={{
        background: 'var(--slate-50)',
        padding: 'var(--s-3)',
        borderRight: '1px solid var(--border-default)',
      }}>
        {carpetas.map((c) => {
          const cnt = contadores?.[c.id] || 0;
          const active = c.id === carpeta;
          return (
            <button
              key={c.id}
              type="button"
              className={`nav-link ${active ? 'active' : ''}`}
              data-testid={`dep-carpeta-${c.id}`}
              onClick={() => onChangeCarpeta(c.id)}
              style={{ width: '100%', textAlign: 'left', cursor: 'pointer', border: 0 }}
            >
              <span aria-hidden="true" style={{ marginRight: 8 }}>{c.icon}</span>
              <span>{c.label}</span>
              {cnt > 0 && <span className="count">{cnt}</span>}
            </button>
          );
        })}
      </aside>
      <section style={{
        borderRight: '1px solid var(--border-default)',
        background: 'white', overflowY: 'auto',
      }}>
        {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
        {error && (
          <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="empty" data-testid="dep-empty" style={{ margin: 'var(--s-3)' }}>
            <p>Sin ítems en esta carpeta.</p>
          </div>
        )}
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            data-testid="dep-item"
            onClick={() => onSelect(it.id)}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: 'var(--s-3) var(--s-4)',
              border: 0,
              borderBottom: '1px solid var(--border-subtle)',
              background: selectedId === it.id ? 'var(--sky-50)' : 'transparent',
              cursor: 'pointer',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13 }}>{it.titulo}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {it.responsable_nombre || it.sub_titulo}
            </div>
          </button>
        ))}
      </section>
      <section style={{ padding: 'var(--s-5)', overflowY: 'auto' }}>
        {selected ? (
          <>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>{selected.titulo}</h2>
            <div className="muted" style={{ fontSize: 12 }}>
              {selected.tipo} · Responsable: {selected.responsable_nombre || '—'}
            </div>
            {selected.descripcion && (
              <p style={{ marginTop: 'var(--s-3)' }}>{selected.descripcion}</p>
            )}
            {selected.ruta_ficha && (
              <button
                type="button"
                className="btn btn-accent"
                onClick={() => onNavigate?.(selected.ruta_ficha)}
                data-testid="dep-abrir-ficha"
                style={{ marginTop: 'var(--s-4)' }}
              >
                Abrir ficha
              </button>
            )}
          </>
        ) : (
          <p className="muted">Seleccione un ítem.</p>
        )}
      </section>
    </div>
  );
}

function CargaEquipoPanel({ session }) {
  const { data, loading, error } = useCargaEquipo(session);

  if (loading) return <p className="muted">Cargando carga del equipo…</p>;
  if (error) {
    return (
      <div className="alert danger" role="alert">
        <div className="body">{error.message || 'Error al cargar.'}</div>
      </div>
    );
  }
  if (!data || !data.usuarios || data.usuarios.length === 0) {
    return (
      <div className="empty" data-testid="carga-empty">
        <p className="muted">Sin datos de carga del equipo aún.</p>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }} data-testid="carga-equipo">
      <table className="data-table">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Cargo</th>
            <th>Tareas abiertas</th>
            <th>Vencimientos próx.</th>
            <th>Productividad</th>
          </tr>
        </thead>
        <tbody>
          {data.usuarios.map((u) => (
            <tr key={u.user_id} data-testid="carga-row">
              <td>{u.nombre}</td>
              <td className="muted">{u.cargo}</td>
              <td className="num">{u.tareas_abiertas ?? 0}</td>
              <td className="num">
                {u.vencimientos_proximos > 0 && (
                  <span className="badge warn">{u.vencimientos_proximos}</span>
                )}
                {!u.vencimientos_proximos && <span className="muted">0</span>}
              </td>
              <td className="num">{u.productividad ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default BuzonDependencia;
