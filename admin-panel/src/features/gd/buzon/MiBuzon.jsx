/**
 * MiBuzon — GD-UI-0016. Layout 3-columnas estilo Gmail.
 *
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │  Carpetas    │  Lista de ítems   │  Detalle del ítem actual │
 *  │  (220 px)    │  (380 px)         │  (resto)                  │
 *  └──────────────────────────────────────────────────────────────┘
 *
 * Cada carpeta es un slot virtual (PQRSD asignadas, correspondencia in/out,
 * tareas, borradores, docs por revisar/aprobar/firmar, notificaciones,
 * alertas). El conteo viene del backend en `contadores`.
 *
 * Click en un ítem actualiza el panel derecho con su detalle. Si el ítem
 * es navegable a una ficha completa (radicado, PQRSD, etc.) el detalle
 * muestra el botón "Abrir ficha".
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { CARPETAS, useMiBuzon } from './useGdBuzon.js';

export function MiBuzon({ session, onNavigate, ...shellProps }) {
  const [carpeta, setCarpeta] = useState('pqrsd');
  const [selectedId, setSelectedId] = useState(null);
  const { items, contadores, loading, error, refresh } =
    useMiBuzon(session, { carpeta });

  const selected = items.find((i) => i.id === selectedId) || items[0];

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Mi buzón' },
      ]}
    >
      <div
        data-testid="mi-buzon-layout"
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 380px 1fr',
          gap: 0,
          minHeight: 'calc(100vh - 120px)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--r-lg)',
          overflow: 'hidden',
          background: 'var(--bg-surface)',
        }}
      >
        <CarpetasPanel
          carpetas={CARPETAS}
          activa={carpeta}
          contadores={contadores}
          onSelect={(c) => { setCarpeta(c); setSelectedId(null); }}
        />
        <ListaPanel
          items={items}
          loading={loading}
          error={error}
          selectedId={selected?.id}
          onSelect={setSelectedId}
          onRefresh={refresh}
        />
        <DetallePanel item={selected} onNavigate={onNavigate} />
      </div>
    </GdShell>
  );
}

function CarpetasPanel({ carpetas, activa, contadores, onSelect }) {
  return (
    <aside
      data-testid="buzon-carpetas"
      style={{
        borderRight: '1px solid var(--border-default)',
        background: 'var(--slate-50)',
        padding: 'var(--s-3)',
      }}
    >
      {carpetas.map((c) => {
        const cnt = contadores?.[c.id] || 0;
        const active = c.id === activa;
        return (
          <button
            key={c.id}
            type="button"
            className={`nav-link ${active ? 'active' : ''}`}
            data-carpeta={c.id}
            data-testid={`carpeta-${c.id}`}
            onClick={() => onSelect(c.id)}
            style={{ width: '100%', textAlign: 'left', cursor: 'pointer', border: 0 }}
          >
            <span aria-hidden="true" style={{ marginRight: 8 }}>{c.icon}</span>
            <span>{c.label}</span>
            {cnt > 0 && <span className="count">{cnt}</span>}
          </button>
        );
      })}
    </aside>
  );
}

function ListaPanel({ items, loading, error, selectedId, onSelect, onRefresh }) {
  return (
    <section
      data-testid="buzon-lista"
      style={{
        borderRight: '1px solid var(--border-default)',
        display: 'flex',
        flexDirection: 'column',
        background: 'white',
      }}
    >
      <div
        style={{
          padding: 'var(--s-3) var(--s-4)',
          borderBottom: '1px solid var(--border-default)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 12,
        }}
      >
        <span className="muted">{items.length} ítem(s)</span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onRefresh}
          data-testid="buzon-refresh"
        >
          Actualizar
        </button>
      </div>
      {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
          <div className="body">{error.message || 'Error al cargar el buzón.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="buzon-empty" style={{ margin: 'var(--s-3)' }}>
          <p>Esta carpeta está vacía.</p>
        </div>
      )}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            data-testid="buzon-item"
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
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>
              {it.titulo || '(sin título)'}
            </div>
            <div className="muted" style={{ fontSize: 12, lineHeight: 1.3 }}>
              {it.sub_titulo}
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
              <span>{it.estado || ''}</span>
              <span>{fmtFecha(it.fecha)}</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function DetallePanel({ item, onNavigate }) {
  if (!item) {
    return (
      <section
        data-testid="buzon-detalle"
        style={{
          display: 'grid',
          placeItems: 'center',
          padding: 'var(--s-6)',
        }}
      >
        <p className="muted">Seleccione un ítem para ver el detalle.</p>
      </section>
    );
  }
  return (
    <section
      data-testid="buzon-detalle"
      style={{ padding: 'var(--s-5)', overflowY: 'auto' }}
    >
      <h2 style={{ marginTop: 0, fontSize: 18 }}>{item.titulo}</h2>
      <div className="muted" style={{ fontSize: 12 }}>
        {item.tipo} · {fmtFecha(item.fecha)}
      </div>
      {item.sub_titulo && (
        <p style={{ marginTop: 'var(--s-3)' }}>{item.sub_titulo}</p>
      )}
      {item.descripcion && (
        <p style={{ fontSize: 13, color: 'var(--fg-secondary)' }}>
          {item.descripcion}
        </p>
      )}
      <div style={{ marginTop: 'var(--s-4)', display: 'flex', gap: 'var(--s-2)' }}>
        {item.ruta_ficha && (
          <button
            type="button"
            className="btn btn-accent"
            data-testid="abrir-ficha"
            onClick={() => onNavigate?.(item.ruta_ficha)}
          >
            Abrir ficha
          </button>
        )}
        {item.tipo === 'tarea' && (
          <button
            type="button"
            className="btn btn-secondary"
            data-testid="abrir-tarea"
            onClick={() => onNavigate?.(`/gd/tareas/${item.id}`)}
          >
            Ver tarea
          </button>
        )}
      </div>
    </section>
  );
}

function fmtFecha(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default MiBuzon;
