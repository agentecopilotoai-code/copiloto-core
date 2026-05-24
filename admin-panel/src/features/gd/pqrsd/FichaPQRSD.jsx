/**
 * FichaPQRSD — GD-UI-0022. 5 tabs + workflow CTAs gated por permiso.
 *
 * Tabs: General / Documentos / Workflow / Trazabilidad / Acciones.
 * El tab Workflow muestra el estado actual de la respuesta + acciones
 * (proyectar / enviar a revisión / revisar / aprobar / firmar / radicar
 * salida / enviar al ciudadano) según permisos del usuario.
 *
 * Reusa: WorkflowTimeline, PQRSDStatusChip, TerminoVencimientoBadge,
 * JustificacionRequiredField.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { PQRSDStatusChip } from '../components/PQRSDStatusChip.jsx';
import { TerminoVencimientoBadge } from '../components/TerminoVencimientoBadge.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { useGdAudit } from '../hooks/useGdAudit.js';
import {
  usePQRSD,
  useProyectarRespuesta,
  useEnviarARevision,
  useRevisarRespuesta,
  useAprobarRespuesta,
  useFirmarRespuesta,
  useRadicarSalidaRespuesta,
  useEnviarRespuesta,
} from './useGdPQRSD.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['General', 'Documentos', 'Workflow', 'Trazabilidad', 'Acciones'];

export function FichaPQRSD({
  session,
  pqrsdId,
  roles = [],
  onNavigate,
  ...shellProps
}) {
  const [tab, setTab] = useState('General');
  const [modal, setModal] = useState(null);
  const { data: pq, loading, error, refresh } = usePQRSD(session, pqrsdId);

  const audit = useGdAudit({
    session, entidadTipo: 'pqrsd', entidadId: pqrsdId,
    enabled: tab === 'Trazabilidad',
  });

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'PQRSD', path: '/gd/pqrsd' },
        { label: pq?.numero_radicado || 'PQRSD' },
      ]}
    >
      {loading && <p className="muted">Cargando PQRSD…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {pq && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 22 }}>
                {pq.numero_radicado}
              </h1>
              <p className="subtitle" style={{ display: 'flex', gap: 'var(--s-3)', alignItems: 'center' }}>
                <PQRSDStatusChip tipo={pq.tipo} />
                <span><strong>{pq.estado}</strong></span>
                {Number.isFinite(pq.dias_restantes) && (
                  <TerminoVencimientoBadge
                    diasRestantes={pq.dias_restantes}
                    terminoTotal={pq.termino_dias}
                    compact
                  />
                )}
              </p>
            </div>
          </div>

          <nav className="tabs" data-testid="pqrsd-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`pqrsd-tab-btn-${t}`}
              >
                {t}
              </button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'General' && <TabGeneral pq={pq} />}
            {tab === 'Documentos' && <TabDocumentos pq={pq} onNavigate={onNavigate} />}
            {tab === 'Workflow' && (
              <TabWorkflow
                session={session} pq={pq} roles={roles}
                onAction={setModal} onRefresh={refresh}
              />
            )}
            {tab === 'Trazabilidad' && (
              <WorkflowTimeline events={audit.events} loading={audit.loading} error={audit.error} />
            )}
            {tab === 'Acciones' && (
              <TabAcciones
                roles={roles} pq={pq}
                onOpen={setModal}
              />
            )}
          </div>

          {modal && (
            <ActionModal
              accion={modal}
              session={session}
              pq={pq}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function TabGeneral({ pq }) {
  return (
    <div data-testid="pqrsd-tab-General">
      <Row label="Tipo" value={`${pq.tipo} · ${pq.tipo_nombre || ''}`} />
      <Row label="Asunto" value={pq.asunto} />
      <Row label="Tercero" value={pq.tercero_nombre || 'Anónimo'} />
      <Row label="Canal" value={pq.canal_nombre} />
      <Row label="Recibida" value={fmtFecha(pq.fecha_radicacion)} />
      <Row label="Vence" value={fmtFecha(pq.fecha_vencimiento)} />
      <Row label="Dependencia actual" value={pq.dependencia_actual_nombre || '—'} />
      <Row label="Responsable" value={pq.responsable_nombre || 'Sin asignar'} />
      {pq.descripcion && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Descripción</div>
          <p style={{ margin: 0 }}>{pq.descripcion}</p>
        </div>
      )}
    </div>
  );
}

function TabDocumentos({ pq, onNavigate }) {
  const docs = pq.documentos || [];
  if (docs.length === 0) {
    return (
      <div className="empty" data-testid="pqrsd-docs-empty">
        <p className="muted">Sin documentos asociados.</p>
      </div>
    );
  }
  return (
    <ul style={{ listStyle: 'none', padding: 0 }} data-testid="pqrsd-docs-list">
      {docs.map((d) => (
        <li
          key={d.id}
          style={{
            padding: 'var(--s-3) 0',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex', gap: 'var(--s-3)', alignItems: 'center',
          }}
        >
          <span style={{ flex: 1 }}>📄 {d.titulo}</span>
          <span className="muted" style={{ fontSize: 12 }}>{d.tipo} · {d.estado}</span>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={() => onNavigate?.(d.ruta || `/gd/documentos/${d.id}`)}
            data-testid="pqrsd-doc-abrir"
          >
            Abrir
          </button>
        </li>
      ))}
    </ul>
  );
}

function TabWorkflow({ pq, roles, onAction }) {
  const respuesta = pq.respuesta_actual;
  return (
    <div data-testid="pqrsd-tab-Workflow">
      {!respuesta ? (
        <div className="alert info">
          <div className="body">
            <div className="title">Aún no hay respuesta proyectada.</div>
            <div>
              {gdCanAny(roles, 'PQRSD-009', 'RW')
                ? 'Puede proyectar una respuesta para iniciar el flujo.'
                : 'Espere a que el profesional responsable proyecte la respuesta.'}
            </div>
            {gdCanAny(roles, 'PQRSD-009', 'RW') && (
              <button
                type="button"
                className="btn btn-accent"
                onClick={() => onAction('proyectar')}
                data-testid="wf-proyectar"
                style={{ marginTop: 'var(--s-3)' }}
              >
                Proyectar respuesta
              </button>
            )}
          </div>
        </div>
      ) : (
        <>
          <Row label="Estado de la respuesta" value={respuesta.estado} />
          <Row label="Proyectada por" value={respuesta.proyectada_por_nombre} />
          <Row label="Fecha proyección" value={fmtFecha(respuesta.fecha_proyeccion)} />
          {respuesta.aprobada_por_nombre && (
            <Row label="Aprobada por" value={respuesta.aprobada_por_nombre} />
          )}
          {respuesta.firmada_por_nombre && (
            <Row label="Firmada por" value={respuesta.firmada_por_nombre} />
          )}
          <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap', marginTop: 'var(--s-4)' }}>
            {respuesta.estado === 'borrador' && gdCanAny(roles, 'PQRSD-012', 'RW') && (
              <button type="button" className="btn btn-accent"
                onClick={() => onAction('enviar-revision')}
                data-testid="wf-enviar-revision"
              >Enviar a revisión</button>
            )}
            {respuesta.estado === 'en_revision' && gdCanAny(roles, 'PQRSD-013', 'RW') && (
              <>
                <button type="button" className="btn btn-accent"
                  onClick={() => onAction('revisar-ok')}
                  data-testid="wf-revisar-ok"
                >Aprobar revisión</button>
                <button type="button" className="btn btn-secondary"
                  onClick={() => onAction('revisar-devolver')}
                  data-testid="wf-revisar-devolver"
                >Devolver al profesional</button>
              </>
            )}
            {respuesta.estado === 'aprobada' && gdCanAny(roles, 'PQRSD-015', 'RW') && (
              <button type="button" className="btn btn-accent"
                onClick={() => onAction('aprobar')}
                data-testid="wf-aprobar"
              >Aprobar definitivamente</button>
            )}
            {respuesta.estado === 'aprobada' && gdCanAny(roles, 'FIR-001', 'RW') && (
              <button type="button" className="btn btn-primary"
                onClick={() => onAction('firmar')}
                data-testid="wf-firmar"
              >Firmar</button>
            )}
            {respuesta.estado === 'firmada' && gdCanAny(roles, 'PQRSD-017', 'RW') && (
              <button type="button" className="btn btn-accent"
                onClick={() => onAction('radicar-salida')}
                data-testid="wf-radicar"
              >Radicar salida</button>
            )}
            {respuesta.estado === 'radicada' && gdCanAny(roles, 'PQRSD-018', 'RW') && (
              <button type="button" className="btn btn-primary"
                onClick={() => onAction('enviar')}
                data-testid="wf-enviar"
              >Enviar al ciudadano</button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function TabAcciones({ roles, onOpen }) {
  return (
    <div data-testid="pqrsd-tab-Acciones">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Operaciones disponibles</h3>
      <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
        {gdCanAny(roles, 'PQRSD-008', 'RW') && (
          <button type="button" className="btn btn-secondary"
            onClick={() => onOpen('reasignar')}
            data-testid="acc-reasignar"
          >Reasignar</button>
        )}
        {gdCanAny(roles, 'PQRSD-019', 'RW') && (
          <button type="button" className="btn btn-secondary"
            onClick={() => onOpen('cerrar')}
            data-testid="acc-cerrar"
          >Cerrar PQRSD</button>
        )}
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 'var(--s-3)' }}>
        Más acciones (traslado, suspensión, reapertura) en el siguiente
        bloque de implementación.
      </p>
    </div>
  );
}

/* ── Modal genérico para acciones del workflow ───────────────────────── */
function ActionModal({ accion, session, pq, onClose, onSuccess }) {
  const META = ACCIONES_META[accion];
  const Hook = META.useHook;
  const hook = Hook ? Hook(session) : null;

  const [justif, setJustif] = useState('');
  const [valid, setValid] = useState(!META.requireJustif);
  const [contenido, setContenido] = useState('');

  async function handle() {
    if (!hook) return;
    const payload = {
      ...(META.requireJustif ? { justificacion: justif } : {}),
      ...(META.requireContenido ? { contenido_borrador: contenido } : {}),
      ...(META.extra || {}),
    };
    try {
      await hook.submit(META.scope === 'respuesta' ? pq.respuesta_actual.id : pq.id, payload);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="pqrsd-action-modal"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()} className="card"
        style={{ width: 480, padding: 'var(--s-5)' }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{META.title}</h2>
        <p className="muted" style={{ fontSize: 13 }}>{META.help}</p>

        {META.requireContenido && (
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>Borrador de respuesta</label>
            <textarea
              className="textarea"
              rows={6}
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              data-testid="modal-contenido"
            />
          </div>
        )}

        {META.requireJustif && (
          <div style={{ marginTop: 'var(--s-3)' }}>
            <JustificacionRequiredField
              value={justif}
              onChange={(v, ok) => { setJustif(v); setValid(ok); }}
              id={`justif-${accion}`}
            />
          </div>
        )}

        {hook?.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className={`btn btn-${META.tone || 'accent'}`}
            disabled={!valid || (META.requireContenido && !contenido.trim()) || hook?.submitting}
            onClick={handle}
            data-testid="modal-confirm"
          >
            {hook?.submitting ? 'Procesando…' : META.cta}
          </button>
        </div>
      </div>
    </div>
  );
}

const ACCIONES_META = {
  proyectar: {
    title: 'Proyectar respuesta',
    help: 'Redacte el borrador inicial. Quedará en estado "borrador" para enviar a revisión.',
    cta: 'Proyectar',
    requireContenido: true,
    requireJustif: false,
    scope: 'pqrsd',
    useHook: useProyectarRespuesta,
    tone: 'accent',
  },
  'enviar-revision': {
    title: 'Enviar a revisión',
    help: 'La respuesta pasa al revisor designado.',
    cta: 'Enviar',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useEnviarARevision,
    tone: 'accent',
  },
  'revisar-ok': {
    title: 'Marcar como revisada (OK)',
    help: 'Indica visto bueno técnico/jurídico.',
    cta: 'Aprobar revisión',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useRevisarRespuesta,
    extra: { resultado: 'ok' },
    tone: 'accent',
  },
  'revisar-devolver': {
    title: 'Devolver al profesional',
    help: 'La respuesta vuelve a "borrador" con sus observaciones.',
    cta: 'Devolver',
    requireJustif: true,
    scope: 'respuesta',
    useHook: useRevisarRespuesta,
    extra: { resultado: 'devolver' },
    tone: 'secondary',
  },
  aprobar: {
    title: 'Aprobar respuesta',
    help: 'Confirma la respuesta para pasar a firma.',
    cta: 'Aprobar',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useAprobarRespuesta,
    tone: 'accent',
  },
  firmar: {
    title: 'Firmar respuesta',
    help: 'Se aplicará la firma electrónica configurada.',
    cta: 'Firmar',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useFirmarRespuesta,
    tone: 'primary',
  },
  'radicar-salida': {
    title: 'Radicar salida',
    help: 'Genera el radicado de salida.',
    cta: 'Radicar',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useRadicarSalidaRespuesta,
    tone: 'accent',
  },
  enviar: {
    title: 'Enviar al ciudadano',
    help: 'Envía la respuesta al canal del solicitante.',
    cta: 'Enviar',
    requireJustif: false,
    scope: 'respuesta',
    useHook: useEnviarRespuesta,
    tone: 'primary',
  },
  reasignar: {
    title: 'Reasignar PQRSD',
    // Nota interna: el UsuarioPicker se conecta en la siguiente entrega
    // (selector con búsqueda por dependencia y rol); por ahora solo
    // se solicita justificación.
    help: 'Indique el motivo de la reasignación. El selector de funcionario se habilita en la próxima entrega.',
    cta: 'Reasignar',
    requireJustif: true,
    scope: 'pqrsd',
    useHook: () => ({ submit: async () => {}, submitting: false, error: null }),
    tone: 'secondary',
  },
  cerrar: {
    title: 'Cerrar PQRSD',
    help: 'Solo cuando la respuesta esté enviada o haya causal de cierre.',
    cta: 'Cerrar',
    requireJustif: true,
    scope: 'pqrsd',
    useHook: () => ({ submit: async () => {}, submitting: false, error: null }),
    tone: 'danger',
  },
};

function Row({ label, value }) {
  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: '180px 1fr',
        padding: '6px 0', borderBottom: '1px dashed var(--border-subtle)',
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

export default FichaPQRSD;
