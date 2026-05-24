/**
 * CorrespondenciaFicha — ficha unificada interna/externa.
 *
 * Tabs:
 *  - General: datos básicos + estado.
 *  - Destinatarios: principal + copias + copias ocultas (GD-UI-0033).
 *  - Workflow (solo externa): CTAs revisar/aprobar/firmar/radicar/enviar.
 *  - Soporte (solo externa): registrar guía postal / email / fax
 *    (GD-UI-0032).
 *  - Trazabilidad: WorkflowTimeline.
 *  - Acciones: anular (GD-UI-0034), reenviar, responder.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { useGdAudit } from '../hooks/useGdAudit.js';
import {
  useCorrespondencia,
  useMarcarLeida,
  useResponderCorrespondencia,
  useReenviarCorrespondencia,
  useEnviarCERevision,
  useRevisarCorrespondencia,
  useAprobarCorrespondencia,
  useFirmarCorrespondencia,
  useRadicarSalidaCorrespondencia,
  useEnviarCorrespondencia,
  useRegistrarSoporteEnvio,
  useAgregarDestinatario,
  useQuitarDestinatario,
  useSolicitarAnulacionCorrespondencia,
} from './useGdCorrespondencia.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function CorrespondenciaFicha({
  session,
  correspondenciaId,
  roles = [],
  onNavigate,
  ...shellProps
}) {
  const { data: c, loading, error, refresh } = useCorrespondencia(session, correspondenciaId);
  const [tab, setTab] = useState('General');
  const [modal, setModal] = useState(null);

  const audit = useGdAudit({
    session, entidadTipo: 'correspondencia', entidadId: correspondenciaId,
    enabled: tab === 'Trazabilidad',
  });

  const esExterna = c?.tipo === 'externa';
  const TABS = ['General', 'Destinatarios'];
  if (esExterna) TABS.push('Workflow', 'Soporte de envío');
  TABS.push('Trazabilidad', 'Acciones');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: esExterna ? 'Correspondencia externa' : 'Correspondencia interna',
          path: `/gd/correspondencia/${esExterna ? 'externa' : 'interna'}` },
        { label: c?.numero || c?.asunto || 'Ficha' },
      ]}
    >
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {c && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontSize: 18 }}>{c.asunto}</h1>
              <p className="subtitle">
                {c.tipo === 'externa' ? 'Externa' : 'Interna'} ·
                {' '}<span className={`badge ${badgeTone(c.estado)}`}>{c.estado}</span>
                {c.numero && <> · <code style={{ fontFamily: 'var(--font-mono)' }}>{c.numero}</code></>}
              </p>
            </div>
          </div>
          <nav className="tabs" data-testid="corresp-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`corresp-tab-btn-${t}`}
              >{t}</button>
            ))}
          </nav>
          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'General' && <TabGeneral c={c} />}
            {tab === 'Destinatarios' && (
              <TabDestinatarios
                session={session}
                c={c}
                roles={roles}
                onRefresh={refresh}
              />
            )}
            {tab === 'Workflow' && esExterna && (
              <TabWorkflow
                session={session}
                c={c}
                roles={roles}
                onAction={setModal}
              />
            )}
            {tab === 'Soporte de envío' && esExterna && (
              <TabSoporte
                session={session}
                c={c}
                onSuccess={refresh}
              />
            )}
            {tab === 'Trazabilidad' && (
              <WorkflowTimeline events={audit.events} loading={audit.loading} error={audit.error} />
            )}
            {tab === 'Acciones' && (
              <TabAcciones c={c} roles={roles} onOpen={setModal} />
            )}
          </div>

          {modal && (
            <ActionModal
              accion={modal}
              session={session}
              c={c}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function TabGeneral({ c }) {
  return (
    <div data-testid="corresp-tab-General">
      <Row label="Tipo" value={c.tipo} />
      <Row label="Asunto" value={c.asunto} />
      <Row label="Origen" value={c.dependencia_origen_nombre || c.remitente_usuario_nombre || '—'} />
      <Row label="Destino" value={c.dependencia_destino_nombre || c.tercero_destinatario_nombre || '—'} />
      <Row label="Estado" value={c.estado} />
      <Row label="Fecha creación" value={fmtFecha(c.created_at || c.fecha)} />
      {c.descripcion && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <div className="muted" style={{ fontSize: 12 }}>Cuerpo</div>
          <p>{c.descripcion}</p>
        </div>
      )}
    </div>
  );
}

function TabDestinatarios({ session, c, roles, onRefresh }) {
  const dests = c.destinatarios || [];
  const puede = gdCanAny(roles, c.tipo === 'externa' ? 'CE-001' : 'CI-001', 'RW');
  const [add, setAdd] = useState({ nombre: '', tipo_copia: 'copia' });
  const agregar = useAgregarDestinatario(session);
  const quitar = useQuitarDestinatario(session);

  async function handleAdd() {
    if (!add.nombre.trim()) return;
    try {
      await agregar.submit(c.id, add);
      setAdd({ nombre: '', tipo_copia: 'copia' });
      onRefresh?.();
    } catch { /* hook */ }
  }

  async function handleRemove(destId) {
    try {
      await quitar.submit(c.id, destId);
      onRefresh?.();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="corresp-tab-Destinatarios">
      {dests.length === 0 ? (
        <div className="empty"><p className="muted">Sin destinatarios adicionales.</p></div>
      ) : (
        <table className="data-table" data-testid="dests-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Tipo copia</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {dests.map((d) => (
              <tr key={d.id} data-testid="dest-row">
                <td>{d.nombre}</td>
                <td>{d.tipo_copia}</td>
                <td style={{ textAlign: 'right' }}>
                  {puede && (
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      onClick={() => handleRemove(d.id)}
                      data-testid={`dest-remove-${d.id}`}
                    >Quitar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {puede && c.estado !== 'enviada' && c.estado !== 'anulada' && (
        <div
          data-testid="dests-add-form"
          style={{
            marginTop: 'var(--s-4)',
            padding: 'var(--s-4)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--r-md)',
          }}
        >
          <h3 style={{ fontSize: 13, marginTop: 0 }}>Agregar destinatario</h3>
          <div className="field">
            <label>Nombre (o UUID de tercero)</label>
            <input
              className="input"
              value={add.nombre}
              onChange={(e) => setAdd((p) => ({ ...p, nombre: e.target.value }))}
              data-testid="dest-add-nombre"
            />
          </div>
          <div className="field" style={{ marginTop: 'var(--s-2)' }}>
            <label>Tipo</label>
            <select
              className="select"
              value={add.tipo_copia}
              onChange={(e) => setAdd((p) => ({ ...p, tipo_copia: e.target.value }))}
              data-testid="dest-add-tipo"
            >
              <option value="principal">Principal</option>
              <option value="copia">Copia</option>
              <option value="copia_oculta">Copia oculta</option>
            </select>
          </div>
          {agregar.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{agregar.error.message || 'Error.'}</div>
            </div>
          )}
          <button
            type="button"
            className="btn btn-accent btn-sm"
            onClick={handleAdd}
            disabled={!add.nombre.trim() || agregar.submitting}
            data-testid="dest-add-submit"
            style={{ marginTop: 'var(--s-3)' }}
          >
            {agregar.submitting ? 'Agregando…' : 'Agregar'}
          </button>
        </div>
      )}
    </div>
  );
}

function TabWorkflow({ c, roles, onAction }) {
  return (
    <div data-testid="corresp-tab-Workflow">
      <Row label="Estado actual" value={c.estado} />
      <Row label="Origen" value={c.dependencia_origen_nombre || '—'} />
      <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)', flexWrap: 'wrap' }}>
        {c.estado === 'borrador' && gdCanAny(roles, 'CE-005', 'RW') && (
          <button type="button" className="btn btn-accent"
            onClick={() => onAction('ce-enviar-revision')}
            data-testid="ce-wf-enviar-revision"
          >Enviar a revisión</button>
        )}
        {c.estado === 'en_revision' && gdCanAny(roles, 'CE-005', 'RW') && (
          <>
            <button type="button" className="btn btn-accent"
              onClick={() => onAction('ce-revisar-ok')}
              data-testid="ce-wf-revisar-ok"
            >Aprobar revisión</button>
            <button type="button" className="btn btn-secondary"
              onClick={() => onAction('ce-revisar-devolver')}
              data-testid="ce-wf-revisar-devolver"
            >Devolver al redactor</button>
          </>
        )}
        {c.estado === 'revisada' && gdCanAny(roles, 'CE-006', 'RW') && (
          <button type="button" className="btn btn-accent"
            onClick={() => onAction('ce-aprobar')}
            data-testid="ce-wf-aprobar"
          >Aprobar</button>
        )}
        {c.estado === 'aprobada' && gdCanAny(roles, 'FIR-001', 'RW') && (
          <button type="button" className="btn btn-primary"
            onClick={() => onAction('ce-firmar')}
            data-testid="ce-wf-firmar"
          >Firmar</button>
        )}
        {c.estado === 'firmada' && gdCanAny(roles, 'VU-002', 'RW') && (
          <button type="button" className="btn btn-accent"
            onClick={() => onAction('ce-radicar')}
            data-testid="ce-wf-radicar"
          >Radicar salida</button>
        )}
        {c.estado === 'radicada_salida' && gdCanAny(roles, 'CE-005', 'RW') && (
          <button type="button" className="btn btn-primary"
            onClick={() => onAction('ce-enviar')}
            data-testid="ce-wf-enviar"
          >Enviar al destinatario</button>
        )}
      </div>
    </div>
  );
}

function TabSoporte({ session, c, onSuccess }) {
  const [soporte, setSoporte] = useState({
    medio: 'correo_postal',
    guia_o_referencia: '',
    fecha_envio: '',
    observacion: '',
  });
  const hook = useRegistrarSoporteEnvio(session);

  async function handle() {
    try {
      await hook.submit(c.id, soporte);
      onSuccess?.();
    } catch { /* hook */ }
  }

  const soportes = c.soportes_envio || [];

  return (
    <div data-testid="corresp-tab-Soporte">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Soportes registrados</h3>
      {soportes.length === 0 ? (
        <div className="empty"><p className="muted">Sin soportes registrados aún.</p></div>
      ) : (
        <table className="data-table" data-testid="soportes-table">
          <thead>
            <tr><th>Medio</th><th>Guía/Ref</th><th>Fecha</th><th>Observación</th></tr>
          </thead>
          <tbody>
            {soportes.map((s) => (
              <tr key={s.id}>
                <td>{s.medio}</td>
                <td className="num">{s.guia_o_referencia}</td>
                <td>{fmtFecha(s.fecha_envio)}</td>
                <td>{s.observacion || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div
        data-testid="soporte-form"
        style={{
          marginTop: 'var(--s-4)',
          padding: 'var(--s-4)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--r-md)',
        }}
      >
        <h3 style={{ fontSize: 14, marginTop: 0 }}>Registrar nuevo soporte</h3>
        <div className="field">
          <label>Medio <span className="req">*</span></label>
          <select
            className="select"
            value={soporte.medio}
            onChange={(e) => setSoporte((p) => ({ ...p, medio: e.target.value }))}
            data-testid="sop-medio"
          >
            <option value="correo_postal">Correo postal (guía)</option>
            <option value="email">Correo electrónico</option>
            <option value="fax">Fax</option>
            <option value="entrega_personal">Entrega personal</option>
            <option value="otro">Otro</option>
          </select>
        </div>
        <div className="field" style={{ marginTop: 'var(--s-2)' }}>
          <label>Guía o referencia</label>
          <input
            className="input"
            value={soporte.guia_o_referencia}
            onChange={(e) => setSoporte((p) => ({ ...p, guia_o_referencia: e.target.value }))}
            data-testid="sop-guia"
          />
        </div>
        <div className="field" style={{ marginTop: 'var(--s-2)' }}>
          <label>Fecha envío</label>
          <input
            type="date"
            className="input"
            value={soporte.fecha_envio}
            onChange={(e) => setSoporte((p) => ({ ...p, fecha_envio: e.target.value }))}
            data-testid="sop-fecha"
          />
        </div>
        <div className="field" style={{ marginTop: 'var(--s-2)' }}>
          <label>Observación</label>
          <textarea
            className="textarea"
            rows={2}
            value={soporte.observacion}
            onChange={(e) => setSoporte((p) => ({ ...p, observacion: e.target.value }))}
            data-testid="sop-obs"
          />
        </div>
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <button
          type="button"
          className="btn btn-accent btn-sm"
          onClick={handle}
          disabled={hook.submitting}
          data-testid="sop-submit"
          style={{ marginTop: 'var(--s-3)' }}
        >
          {hook.submitting ? 'Registrando…' : 'Registrar soporte'}
        </button>
      </div>
    </div>
  );
}

function TabAcciones({ c, roles, onOpen }) {
  const esInterna = c.tipo === 'interna';
  const esExterna = c.tipo === 'externa';
  const puedeAnular = gdCanAny(roles, esExterna ? 'CE-009' : 'CI-001', 'RW');
  const puedeResponder = gdCanAny(roles, 'CI-001', 'RW');
  return (
    <div data-testid="corresp-tab-Acciones">
      <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
        {esInterna && puedeResponder && (
          <button type="button" className="btn btn-secondary"
            onClick={() => onOpen('responder')}
            data-testid="acc-responder"
          >Responder</button>
        )}
        {esInterna && puedeResponder && (
          <button type="button" className="btn btn-secondary"
            onClick={() => onOpen('reenviar')}
            data-testid="acc-reenviar"
          >Reenviar</button>
        )}
        {puedeAnular && c.estado !== 'anulada' && (
          <button type="button" className="btn btn-danger"
            onClick={() => onOpen('ce-anular')}
            data-testid="acc-anular"
          >Solicitar anulación</button>
        )}
      </div>
    </div>
  );
}

/* ───────── Modales ────────── */

function ActionModal({ accion, session, c, onClose, onSuccess }) {
  const META = ACCIONES_META[accion];
  const hook = META.useHook(session);

  const [justif, setJustif] = useState('');
  const [valid, setValid] = useState(!META.requireJustif);
  const [extra, setExtra] = useState({});

  async function handle() {
    const payload = {
      ...(META.requireJustif ? { justificacion: justif, motivo: justif } : {}),
      ...(META.extra || {}),
      ...extra,
    };
    try {
      if (META.scope === 'anular') {
        await hook.submit(c.id, justif);
      } else {
        await hook.submit(c.id, payload);
      }
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="corresp-modal"
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
        {META.requireMensaje && (
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>Mensaje</label>
            <textarea
              className="textarea"
              rows={4}
              value={extra.mensaje || ''}
              onChange={(e) => setExtra((p) => ({ ...p, mensaje: e.target.value }))}
              data-testid="modal-mensaje"
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
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className={`btn btn-${META.tone || 'accent'}`}
            disabled={!valid || hook.submitting}
            onClick={handle}
            data-testid="modal-confirm"
          >
            {hook.submitting ? 'Procesando…' : META.cta}
          </button>
        </div>
      </div>
    </div>
  );
}

const ACCIONES_META = {
  responder: {
    title: 'Responder comunicación',
    help: 'Redacte la respuesta. Se enviará al remitente original.',
    cta: 'Responder',
    requireMensaje: true,
    requireJustif: false,
    useHook: useResponderCorrespondencia,
    tone: 'accent',
  },
  reenviar: {
    title: 'Reenviar comunicación',
    help: 'Reenvía a otro destinatario. Indique el motivo.',
    cta: 'Reenviar',
    requireJustif: true,
    useHook: useReenviarCorrespondencia,
    tone: 'secondary',
  },
  'ce-enviar-revision': {
    title: 'Enviar a revisión',
    help: 'La correspondencia pasa al revisor.',
    cta: 'Enviar',
    requireJustif: false,
    useHook: useEnviarCERevision,
    tone: 'accent',
  },
  'ce-revisar-ok': {
    title: 'Aprobar revisión',
    help: 'Visto bueno técnico/jurídico.',
    cta: 'Aprobar revisión',
    requireJustif: false,
    extra: { resultado: 'ok' },
    useHook: useRevisarCorrespondencia,
    tone: 'accent',
  },
  'ce-revisar-devolver': {
    title: 'Devolver al redactor',
    help: 'La correspondencia regresa a estado borrador con sus observaciones.',
    cta: 'Devolver',
    requireJustif: true,
    extra: { resultado: 'devolver' },
    useHook: useRevisarCorrespondencia,
    tone: 'secondary',
  },
  'ce-aprobar': {
    title: 'Aprobar correspondencia',
    help: 'Confirma para pasar a firma.',
    cta: 'Aprobar',
    requireJustif: false,
    useHook: useAprobarCorrespondencia,
    tone: 'accent',
  },
  'ce-firmar': {
    title: 'Firmar correspondencia',
    help: 'Aplica la firma electrónica.',
    cta: 'Firmar',
    requireJustif: false,
    useHook: useFirmarCorrespondencia,
    tone: 'primary',
  },
  'ce-radicar': {
    title: 'Radicar salida',
    help: 'Genera el radicado de salida desde Ventanilla Única.',
    cta: 'Radicar',
    requireJustif: false,
    useHook: useRadicarSalidaCorrespondencia,
    tone: 'accent',
  },
  'ce-enviar': {
    title: 'Enviar al destinatario',
    help: 'Despacha al destinatario externo.',
    cta: 'Enviar',
    requireJustif: false,
    useHook: useEnviarCorrespondencia,
    tone: 'primary',
  },
  'ce-anular': {
    title: 'Solicitar anulación',
    help: 'Sigue el flujo de aprobación equivalente a anulación de radicado (RNF-058).',
    cta: 'Solicitar anulación',
    requireJustif: true,
    scope: 'anular',
    useHook: useSolicitarAnulacionCorrespondencia,
    tone: 'danger',
  },
};

function badgeTone(estado) {
  if (estado === 'enviada' || estado === 'leida' || estado === 'firmada' || estado === 'radicada_salida') return 'ok';
  if (estado === 'anulada' || estado === 'devuelta') return 'danger';
  if (estado === 'borrador') return 'neutral';
  return 'info';
}

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

export default CorrespondenciaFicha;
