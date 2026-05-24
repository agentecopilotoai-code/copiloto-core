/**
 * DocumentoFicha — GD-UI-0036 + GD-UI-0038.
 *
 * Tabs: General / Versiones / Trazabilidad / Acciones.
 * Acciones: nueva versión (reemplazo), anular (con motivo).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { useGdAudit } from '../hooks/useGdAudit.js';
import {
  useDocumento,
  useVersionesDocumento,
  useNuevaVersionDocumento,
  useAnularDocumento,
} from './useGdDocumentos.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['General', 'Versiones', 'Trazabilidad', 'Acciones'];

export function DocumentoFicha({
  session, documentoId, roles = [], onNavigate, ...shellProps
}) {
  const [tab, setTab] = useState('General');
  const [modal, setModal] = useState(null);
  const { data: doc, loading, error, refresh } = useDocumento(session, documentoId);
  const ver = useVersionesDocumento(session, documentoId, {
    enabled: tab === 'Versiones',
  });
  const audit = useGdAudit({
    session, entidadTipo: 'documento', entidadId: documentoId,
    enabled: tab === 'Trazabilidad',
  });

  const puedeReemplazar = gdCanAny(roles, 'DOC-005', 'RW');
  const puedeAnular = gdCanAny(roles, 'DOC-006', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Biblioteca', path: '/gd/documentos' },
        { label: doc?.titulo || 'Documento' },
      ]}
    >
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {doc && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontSize: 18 }}>{doc.titulo}</h1>
              <p className="subtitle">
                {doc.tipo} · v{doc.version_actual} ·{' '}
                <span className={`badge ${badgeTone(doc.estado)}`}>{doc.estado}</span>
              </p>
            </div>
            <div className="actions">
              {doc.archivo_url && (
                <a
                  href={doc.archivo_url}
                  className="btn btn-secondary"
                  download
                  data-testid="doc-descargar"
                >Descargar</a>
              )}
            </div>
          </div>

          <nav className="tabs" data-testid="doc-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`doc-tab-btn-${t}`}
              >{t}</button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'General' && (
              <div data-testid="doc-tab-General">
                <Row label="Título" value={doc.titulo} />
                <Row label="Tipo" value={doc.tipo} />
                <Row label="Versión actual" value={`v${doc.version_actual}`} />
                <Row label="Estado" value={doc.estado} />
                <Row label="Autor" value={doc.autor_nombre} />
                <Row label="Creado" value={fmtFecha(doc.created_at)} />
                <Row label="Modificado" value={fmtFecha(doc.updated_at)} />
                {doc.descripcion && (
                  <div style={{ marginTop: 'var(--s-3)' }}>
                    <div className="muted" style={{ fontSize: 12 }}>Descripción</div>
                    <p>{doc.descripcion}</p>
                  </div>
                )}
              </div>
            )}
            {tab === 'Versiones' && (
              <TabVersiones items={ver.items} loading={ver.loading} error={ver.error} />
            )}
            {tab === 'Trazabilidad' && (
              <WorkflowTimeline
                events={audit.events}
                loading={audit.loading}
                error={audit.error}
              />
            )}
            {tab === 'Acciones' && (
              <div data-testid="doc-tab-Acciones">
                <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
                  {puedeReemplazar && doc.estado !== 'anulado' && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setModal('nueva-version')}
                      data-testid="acc-nueva-version"
                    >Cargar nueva versión</button>
                  )}
                  {puedeAnular && doc.estado !== 'anulado' && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => setModal('anular')}
                      data-testid="acc-anular-doc"
                    >Anular documento</button>
                  )}
                </div>
              </div>
            )}
          </div>

          {modal === 'nueva-version' && (
            <NuevaVersionModal
              session={session}
              doc={doc}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
          {modal === 'anular' && (
            <AnularDocModal
              session={session}
              doc={doc}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function TabVersiones({ items, loading, error }) {
  if (loading) return <p className="muted">Cargando versiones…</p>;
  if (error) {
    return (
      <div className="alert danger" role="alert">
        <div className="body">{error.message || 'Error.'}</div>
      </div>
    );
  }
  if (!items || items.length === 0) {
    return (
      <div className="empty" data-testid="versiones-empty">
        <p className="muted">Sin versiones registradas.</p>
      </div>
    );
  }
  return (
    <table className="data-table" data-testid="versiones-table">
      <thead>
        <tr>
          <th>Versión</th>
          <th>Autor</th>
          <th>Fecha</th>
          <th>Motivo</th>
        </tr>
      </thead>
      <tbody>
        {items.map((v) => (
          <tr key={v.id} data-testid="version-row">
            <td className="num">v{v.numero_version}</td>
            <td>{v.autor_nombre}</td>
            <td>{fmtFecha(v.created_at)}</td>
            <td>{v.motivo || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NuevaVersionModal({ session, doc, onClose, onSuccess }) {
  const [archivoId, setArchivoId] = useState('');
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useNuevaVersionDocumento(session);

  async function handle() {
    try {
      await hook.submit(doc.id, {
        archivo_digital_id: archivoId,
        motivo,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Nueva versión del documento" onClose={onClose}>
      <p className="muted" style={{ fontSize: 13 }}>
        La versión anterior queda preservada en el historial.
      </p>
      <div className="field">
        <label>UUID del archivo digital (subir primero) <span className="req">*</span></label>
        <input
          className="input"
          value={archivoId}
          onChange={(e) => setArchivoId(e.target.value)}
          data-testid="nuevaver-archivo"
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo de la nueva versión"
          id="motivo-nueva-version"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button"
          className="btn btn-accent"
          disabled={!archivoId.trim() || !valid || hook.submitting}
          onClick={handle}
          data-testid="nuevaver-submit"
        >{hook.submitting ? 'Guardando…' : 'Crear versión'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function AnularDocModal({ session, doc, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useAnularDocumento(session);

  async function handle() {
    try {
      await hook.submit(doc.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Anular documento" onClose={onClose}>
      <p className="muted" style={{ fontSize: 13 }}>
        La anulación es irreversible. El documento permanece accesible
        para auditoría con marca "ANULADO".
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de anulación"
        id="motivo-anular-doc"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button"
          className="btn btn-danger-solid"
          disabled={!valid || hook.submitting}
          onClick={handle}
          data-testid="anular-doc-submit"
        >{hook.submitting ? 'Anulando…' : 'Anular'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, children, onClose }) {
  return (
    <div
      role="dialog" aria-modal="true" data-testid="doc-modal"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()} className="card"
        style={{ width: 480, padding: 'var(--s-5)' }}>
        <h2 style={{ margin: 0, fontSize: 16, marginBottom: 'var(--s-3)' }}>{title}</h2>
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

function badgeTone(estado) {
  if (estado === 'aprobado' || estado === 'firmado') return 'ok';
  if (estado === 'anulado') return 'danger';
  if (estado === 'borrador') return 'neutral';
  return 'info';
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

export default DocumentoFicha;
