/**
 * ExpedienteFicha — GD-UI-0049. Expediente electrónico.
 *
 * Tabs:
 *  - General: metadatos + serie + ubicación TRD
 *  - Documentos: índice automático + foliación
 *  - Trazabilidad: audit trail completo
 *  - Acciones: agregar doc, clasificar, cerrar, transferir, reabrir
 *
 * Integridad (RNF-009):
 *  - Foliación automática server-side (la UI muestra el folio asignado).
 *  - Cada documento se asocia con timestamp + responsable.
 *  - Acciones irreversibles (cierre, transferencia) requieren motivo.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { useGdAudit } from '../hooks/useGdAudit.js';
import {
  useExpediente, useDocumentosExpediente, useIndiceExpediente,
  useAgregarDocumentoExp, useQuitarDocumentoExp,
  useReabrirExpediente,
} from './useGdExpedientes.js';
import { CerrarExpedienteModal } from './CerrarExpedienteModal.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['General', 'Documentos', 'Trazabilidad', 'Acciones'];

export function ExpedienteFicha({
  session, expedienteId, roles = [], onNavigate, ...shellProps
}) {
  const [tab, setTab] = useState('General');
  const [modal, setModal] = useState(null);
  const { data: exp, loading, error, refresh } =
    useExpediente(session, expedienteId);
  const docs = useDocumentosExpediente(session, expedienteId, {
    enabled: tab === 'Documentos',
  });
  const indice = useIndiceExpediente(session, expedienteId, {
    enabled: tab === 'Documentos',
  });
  const audit = useGdAudit({
    session, entidadTipo: 'expediente', entidadId: expedienteId,
    enabled: tab === 'Trazabilidad',
  });
  const puedeEditar = gdCanAny(roles, 'EXP-001', 'RW');

  const isCerrado = exp?.estado === 'cerrado' || exp?.estado === 'transferido';

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Expedientes', path: '/gd/expedientes' },
        { label: exp?.codigo || 'Expediente' },
      ]}
    >
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {exp && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontSize: 18 }}>
                {exp.codigo} — {exp.titulo}
              </h1>
              <p className="subtitle">
                {exp.serie_nombre || '—'} · {' '}
                <span className={`badge ${badgeTone(exp.estado)}`}>{exp.estado}</span>
                {' '}· {exp.total_documentos ?? 0} documento(s)
              </p>
            </div>
          </div>

          <nav className="tabs" data-testid="exp-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`exp-tab-btn-${t}`}
              >{t}</button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'General' && (
              <div data-testid="exp-tab-General">
                <Row label="Código" value={exp.codigo} />
                <Row label="Título" value={exp.titulo} />
                <Row label="Serie" value={exp.serie_codigo
                  ? `${exp.serie_codigo} — ${exp.serie_nombre || ''}` : '—'} />
                <Row label="Subserie" value={exp.subserie_codigo
                  ? `${exp.subserie_codigo} — ${exp.subserie_nombre || ''}` : '—'} />
                <Row label="Dependencia" value={exp.dependencia_nombre} />
                <Row label="Estado" value={exp.estado} />
                <Row label="Apertura" value={fmt(exp.fecha_apertura)} />
                {exp.fecha_cierre && (
                  <Row label="Cierre" value={fmt(exp.fecha_cierre)} />
                )}
                {exp.descripcion && (
                  <div style={{ marginTop: 'var(--s-3)' }}>
                    <div className="muted" style={{ fontSize: 12 }}>Descripción</div>
                    <p>{exp.descripcion}</p>
                  </div>
                )}
                {exp.responsable_nombre && (
                  <Row label="Responsable" value={exp.responsable_nombre} />
                )}
              </div>
            )}

            {tab === 'Documentos' && (
              <TabDocumentos
                items={docs.items}
                indice={indice.data}
                loading={docs.loading || indice.loading}
                error={docs.error || indice.error}
                puedeEditar={puedeEditar && !isCerrado}
                onView={(id) => onNavigate?.(`/gd/documentos/${id}`)}
                onQuitar={(id) => setModal({ tipo: 'quitar', documentoId: id })}
              />
            )}

            {tab === 'Trazabilidad' && (
              <WorkflowTimeline
                events={audit.events}
                loading={audit.loading}
                error={audit.error}
              />
            )}

            {tab === 'Acciones' && (
              <div data-testid="exp-tab-Acciones">
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--s-2)' }}>
                  {puedeEditar && !isCerrado && (
                    <>
                      <button
                        type="button"
                        className="btn btn-accent"
                        onClick={() => setModal({ tipo: 'agregar' })}
                        data-testid="exp-agregar-doc"
                      >+ Agregar documento</button>
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => setModal({ tipo: 'cerrar' })}
                        data-testid="exp-cerrar"
                      >Cerrar expediente</button>
                    </>
                  )}
                  {puedeEditar && exp.estado === 'cerrado' && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setModal({ tipo: 'reabrir' })}
                      data-testid="exp-reabrir"
                    >Reabrir expediente</button>
                  )}
                </div>
                {isCerrado && (
                  <p className="muted" style={{ fontSize: 13, marginTop: 'var(--s-3) ' }}>
                    El expediente está {exp.estado}. No se pueden agregar
                    o quitar documentos.
                  </p>
                )}
              </div>
            )}
          </div>

          {modal?.tipo === 'agregar' && (
            <AgregarDocModal
              session={session}
              expedienteId={expedienteId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); docs.refresh?.(); }}
            />
          )}
          {modal?.tipo === 'quitar' && (
            <QuitarDocModal
              session={session}
              expedienteId={expedienteId}
              documentoId={modal.documentoId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); docs.refresh?.(); }}
            />
          )}
          {modal?.tipo === 'cerrar' && (
            <CerrarExpedienteModal
              session={session}
              expedienteId={expedienteId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
          {modal?.tipo === 'reabrir' && (
            <ReabrirExpModal
              session={session}
              expedienteId={expedienteId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function TabDocumentos({ items, indice, loading, error, puedeEditar, onView, onQuitar }) {
  if (loading) return <p className="muted">Cargando documentos…</p>;
  if (error) {
    return (
      <div className="alert danger" role="alert">
        <div className="body">{error.message || 'Error.'}</div>
      </div>
    );
  }
  if (!items || items.length === 0) {
    return (
      <div className="empty" data-testid="exp-docs-empty">
        <p className="muted">El expediente aún no tiene documentos asociados.</p>
      </div>
    );
  }
  return (
    <div data-testid="exp-tab-Documentos">
      {indice && (
        <p className="muted" style={{ fontSize: 12, marginBottom: 'var(--s-3)' }}>
          Índice generado el {fmt(indice.generado_en)} · {' '}
          <strong>{indice.total_folios || items.length}</strong> folio(s).
        </p>
      )}
      <table className="data-table" data-testid="exp-docs-table">
        <thead>
          <tr>
            <th>Folio</th>
            <th>Documento</th>
            <th>Tipo</th>
            <th>Incorporado</th>
            <th>Responsable</th>
            {puedeEditar && <th>Acciones</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id || d.documento_id} data-testid="exp-doc-row">
              <td className="num">{d.folio || '—'}</td>
              <td>
                <button
                  type="button" className="link-as-button"
                  onClick={() => onView?.(d.documento_id || d.id)}
                  data-testid="exp-doc-link"
                >{d.titulo || d.documento_titulo}</button>
              </td>
              <td>{d.tipo || '—'}</td>
              <td>{fmt(d.incorporado_en)}</td>
              <td>{d.responsable_nombre || '—'}</td>
              {puedeEditar && (
                <td>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => onQuitar?.(d.documento_id || d.id)}
                    data-testid="exp-quitar-doc"
                  >Quitar</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AgregarDocModal({ session, expedienteId, onClose, onSuccess }) {
  const [docId, setDocId] = useState('');
  const hook = useAgregarDocumentoExp(session);

  async function handle() {
    try {
      await hook.submit(expedienteId, docId.trim());
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Agregar documento al expediente" onClose={onClose} testid="exp-agregar-modal">
      <div className="field">
        <label>UUID del documento <span className="req">*</span></label>
        <input
          className="input" value={docId}
          onChange={(e) => setDocId(e.target.value)}
          placeholder="Pegue aquí el UUID del documento de la biblioteca"
          data-testid="exp-agregar-uuid"
        />
        <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          El sistema asigna folio consecutivo automáticamente y registra
          la incorporación en el índice del expediente.
        </p>
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-accent"
          disabled={!docId.trim() || hook.submitting} onClick={handle}
          data-testid="exp-agregar-submit"
        >{hook.submitting ? 'Agregando…' : 'Agregar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function QuitarDocModal({ session, expedienteId, documentoId, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useQuitarDocumentoExp(session);

  async function handle() {
    try {
      await hook.submit(expedienteId, documentoId, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Quitar documento del expediente" onClose={onClose} testid="exp-quitar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        El documento se desasocia del expediente pero permanece en la
        biblioteca. El cambio queda registrado en la trazabilidad.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo del retiro"
        id="exp-quitar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="exp-quitar-submit"
        >{hook.submitting ? 'Quitando…' : 'Quitar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ReabrirExpModal({ session, expedienteId, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useReabrirExpediente(session);

  async function handle() {
    try {
      await hook.submit(expedienteId, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Reabrir expediente" onClose={onClose} testid="exp-reabrir-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        El expediente vuelve a estado abierto. La reapertura debe estar
        justificada y queda en auditoría.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de reapertura"
        id="exp-reabrir-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-secondary"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="exp-reabrir-submit"
        >{hook.submitting ? 'Reabriendo…' : 'Reabrir'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div
      role="dialog" aria-modal="true" data-testid={testid}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 520, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ModalFoot({ onClose, children }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
      <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '180px 1fr',
      padding: '6px 0', borderBottom: '1px dashed var(--border-subtle)',
      fontSize: 14,
    }}>
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span>{value || '—'}</span>
    </div>
  );
}

function badgeTone(estado) {
  if (estado === 'abierto') return 'info';
  if (estado === 'cerrado') return 'ok';
  if (estado === 'transferido') return 'neutral';
  return 'info';
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default ExpedienteFicha;
