/**
 * TareaFicha — GD-UI-0018. Ficha genérica de una tarea con acciones del
 * workflow y WorkflowTimeline.
 *
 * Acciones: iniciar | devolver | finalizar | reasignar | escalar.
 * Cada una abre un modal de confirmación con (opcional) justificación.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { UsuarioPicker } from './UsuarioPicker.jsx';
import { useTarea, useAccionTarea } from './useGdBuzon.js';
import { useGdAudit } from '../hooks/useGdAudit.js';

const ACCIONES = [
  { id: 'iniciar', label: 'Iniciar', requireJustif: false, tone: 'accent' },
  { id: 'devolver', label: 'Devolver', requireJustif: true, tone: 'secondary' },
  { id: 'finalizar', label: 'Finalizar', requireJustif: false, tone: 'primary' },
  { id: 'reasignar', label: 'Reasignar', requireJustif: true, tone: 'secondary', requirePicker: true },
  { id: 'escalar', label: 'Escalar', requireJustif: true, tone: 'danger' },
];

export function TareaFicha({
  session,
  tareaId,
  onNavigate,
  ...shellProps
}) {
  const { data: tarea, loading, error, refresh } = useTarea(session, tareaId);
  const accion = useAccionTarea(session);
  const [modal, setModal] = useState(null);

  const { events, loading: audLoading } = useGdAudit({
    session,
    entidadTipo: 'tarea',
    entidadId: tareaId,
  });

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Mi buzón', path: '/gd/buzon' },
        { label: tarea?.titulo || 'Tarea' },
      ]}
    >
      {loading && <p className="muted">Cargando tarea…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {tarea && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1>{tarea.titulo}</h1>
              <p className="subtitle">
                Tarea {tarea.tipo} · Estado <strong>{tarea.estado}</strong>
                {tarea.vence_en && <> · Vence {fmtFecha(tarea.vence_en)}</>}
              </p>
            </div>
            <div className="actions" data-testid="tarea-actions">
              {ACCIONES
                .filter((a) => (tarea.acciones_permitidas || []).includes(a.id))
                .map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className={`btn btn-${a.tone}`}
                    onClick={() => setModal(a)}
                    data-testid={`btn-${a.id}`}
                  >
                    {a.label}
                  </button>
                ))}
            </div>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Detalle</h3>
            <Row label="Tipo" value={tarea.tipo} />
            <Row label="Estado" value={tarea.estado} />
            <Row label="Responsable actual" value={tarea.responsable_nombre || '—'} />
            <Row label="Asignada el" value={fmtFecha(tarea.asignada_en)} />
            <Row label="Vence" value={fmtFecha(tarea.vence_en)} />
            {tarea.descripcion && (
              <>
                <div className="muted" style={{ fontSize: 12, marginTop: 'var(--s-3)' }}>Descripción</div>
                <p style={{ margin: 0 }}>{tarea.descripcion}</p>
              </>
            )}
            {tarea.entidad_relacionada && (
              <div style={{ marginTop: 'var(--s-3)' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onNavigate?.(tarea.entidad_relacionada.ruta)}
                  data-testid="abrir-entidad"
                >
                  Abrir {tarea.entidad_relacionada.tipo} relacionado
                </button>
              </div>
            )}
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginTop: 'var(--s-4)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Trazabilidad</h3>
            <WorkflowTimeline events={events} loading={audLoading} />
          </div>

          {modal && (
            <AccionModal
              accion={modal}
              session={session}
              tarea={tarea}
              hook={accion}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function AccionModal({ accion, session, tarea, hook, onClose, onSuccess }) {
  const [justif, setJustif] = useState('');
  const [valid, setValid] = useState(!accion.requireJustif);
  const [nuevoUserId, setNuevoUserId] = useState('');

  const ok = (accion.requireJustif ? valid : true) &&
             (accion.requirePicker ? Boolean(nuevoUserId) : true);

  async function handle() {
    try {
      await hook.submit(tarea.id, accion.id, {
        justificacion: accion.requireJustif ? justif : undefined,
        nuevo_responsable_user_id: accion.requirePicker ? nuevoUserId : undefined,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="tarea-modal"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card"
        style={{ width: 460, padding: 'var(--s-5)' }}
      >
        <h2 style={{ margin: 0, fontSize: 16 }}>{accion.label} tarea</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          {accion.id === 'escalar'
            ? 'Escalar al jefe de dependencia. Notifica al destinatario y queda auditado.'
            : `${accion.label} la tarea actual. Esta acción queda registrada en la trazabilidad.`}
        </p>

        {accion.requirePicker && (
          <UsuarioPicker
            session={session}
            dependenciaId={tarea.dependencia_id}
            rol={tarea.rol_compatible}
            value={nuevoUserId}
            onChange={setNuevoUserId}
            label="Nuevo responsable"
            excluir={[tarea.responsable_user_id]}
            testId="modal-usuario-picker"
          />
        )}

        {accion.requireJustif && (
          <JustificacionRequiredField
            value={justif}
            onChange={(v, ok2) => { setJustif(v); setValid(ok2); }}
            id={`justif-${accion.id}`}
          />
        )}

        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className={`btn btn-${accion.tone}`}
            onClick={handle}
            disabled={!ok || hook.submitting}
            data-testid="tarea-modal-confirm"
          >
            {hook.submitting ? 'Ejecutando…' : accion.label}
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: '180px 1fr',
        padding: '6px 0',
        borderBottom: '1px dashed var(--border-subtle)',
        fontSize: 14,
      }}
    >
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span>{value || '—'}</span>
    </div>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default TareaFicha;
