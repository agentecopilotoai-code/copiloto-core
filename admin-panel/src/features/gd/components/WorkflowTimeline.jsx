/**
 * WorkflowTimeline — timeline visual de eventos auditables.
 *
 * Renderiza una lista cronológica de `core.evento_auditoria` para una
 * entidad GD. Cada evento muestra: tipo + actor + dependencia/cargo del
 * momento + fecha + criticidad.
 *
 * Carga datos vía `useGdAudit` o recibe ya cargado via prop `events`.
 *
 * RNF-006/009/012: trazabilidad completa con snapshot del rol/cargo al
 * momento del evento.
 */
import React from 'react';

const CRITICIDAD_TONE = Object.freeze({
  baja: 'neutral',
  media: 'info',
  alta: 'warn',
  critica: 'danger',
});

export function WorkflowTimeline({
  events = [],
  loading = false,
  error = null,
  empty = 'Sin eventos registrados.',
}) {
  if (loading) return <p className="muted">Cargando trazabilidad…</p>;
  if (error) {
    return (
      <div className="alert danger" role="alert">
        <div className="body">
          <div className="title">No se pudo cargar la trazabilidad.</div>
          <div>{error.message || 'Intente nuevamente más tarde.'}</div>
        </div>
      </div>
    );
  }
  if (!events || events.length === 0) {
    return (
      <div className="empty" data-testid="timeline-empty">
        <p className="muted">{empty}</p>
      </div>
    );
  }

  return (
    <ol
      className="wf-timeline"
      data-testid="workflow-timeline"
      style={{
        listStyle: 'none',
        margin: 0,
        padding: 0,
        borderLeft: '2px solid var(--border-default)',
      }}
    >
      {events.map((e) => (
        <li
          key={e.id}
          className="wf-event"
          style={{
            position: 'relative',
            paddingLeft: 'var(--s-5)',
            paddingTop: 'var(--s-3)',
            paddingBottom: 'var(--s-3)',
          }}
        >
          <span
            className="wf-dot"
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: -7,
              top: 18,
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: 'var(--bg-surface)',
              border: '2px solid var(--accent-base)',
            }}
          />
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--s-3)',
              marginBottom: 4,
            }}
          >
            <strong>{e.tipo_evento}</strong>
            <span className={`badge ${CRITICIDAD_TONE[e.criticidad] || 'neutral'}`}>
              {e.criticidad || 'media'}
            </span>
            <span className="muted" style={{ marginLeft: 'auto', fontSize: 12 }}>
              {fmtFecha(e.created_at)}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 12.5 }}>
            👤 {e.actor_nombre || 'Sistema'}
            {e.actor_rol && <> · {e.actor_rol}</>}
            {e.actor_dependencia_nombre && <> · 📁 {e.actor_dependencia_nombre}</>}
            {e.accion && <> · {e.accion}</>}
          </div>
          {e.justificacion && (
            <div
              style={{
                marginTop: 6,
                fontSize: 13,
                fontStyle: 'italic',
                color: 'var(--fg-secondary)',
              }}
            >
              «{e.justificacion}»
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default WorkflowTimeline;
