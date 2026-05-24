/**
 * PorFirmar — GD-UI-0041. Bandeja "Por firmar".
 *
 * Lista documentos pendientes de firma para el usuario actual.
 * Gated por PERM-FIR-001 (firmante o jefe_dependencia).
 * Acciones: Firmar (digital), Firma escaneada, Rechazar (con motivo).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePorFirmar,
  useFirmarDocumento,
  useRechazarFirmaDocumento,
} from './useGdFirmas.js';
import { FirmaEscaneadaModal } from './FirmaEscaneadaModal.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function PorFirmar({ session, roles = [], onNavigate, ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, total, loading, error, refresh } =
    usePorFirmar(session, filtros);
  const [escaneadaPara, setEscaneadaPara] = useState(null);
  const [rechazoPara, setRechazoPara] = useState(null);
  const puedeFirmar = gdCanAny(roles, 'FIR-001', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Por firmar' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Documentos por firmar</h1>
          <p className="subtitle">
            {total} documento(s) pendiente(s) de su firma.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="firmar-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!puedeFirmar && (
        <div className="alert warning" role="alert" data-testid="firmar-no-perm">
          <div className="body">
            No tiene asignado el rol Firmante. Solicite habilitación al administrador.
          </div>
        </div>
      )}

      {puedeFirmar && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
            <div style={{ display: 'flex', gap: 'var(--s-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Tipo documental</label>
                <input
                  className="input"
                  value={filtros.tipo || ''}
                  onChange={(e) => setFiltros({ ...filtros, tipo: e.target.value || undefined })}
                  data-testid="firmar-filter-tipo"
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Dependencia</label>
                <input
                  className="input"
                  value={filtros.dependencia || ''}
                  onChange={(e) => setFiltros({ ...filtros, dependencia: e.target.value || undefined })}
                  data-testid="firmar-filter-dep"
                />
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
            {error && (
              <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
                <div className="body">{error.message || 'Error.'}</div>
              </div>
            )}
            {!loading && !error && items.length === 0 && (
              <div className="empty" data-testid="firmar-empty" style={{ margin: 'var(--s-4)' }}>
                <p>Sin documentos por firmar.</p>
              </div>
            )}
            {items.length > 0 && (
              <table className="data-table" data-testid="firmar-table">
                <thead>
                  <tr>
                    <th>Documento</th>
                    <th>Tipo</th>
                    <th>Solicitante</th>
                    <th>Solicitado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((d) => (
                    <RowFirma
                      key={d.id}
                      doc={d}
                      session={session}
                      onView={() => onNavigate?.(`/gd/documentos/${d.documento_id || d.id}`)}
                      onEscaneada={() => setEscaneadaPara(d)}
                      onRechazar={() => setRechazoPara(d)}
                      onChanged={refresh}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {escaneadaPara && (
        <FirmaEscaneadaModal
          session={session}
          documentoId={escaneadaPara.documento_id || escaneadaPara.id}
          onClose={() => setEscaneadaPara(null)}
          onSuccess={() => { setEscaneadaPara(null); refresh(); }}
        />
      )}

      {rechazoPara && (
        <RechazoModal
          session={session}
          documentoId={rechazoPara.documento_id || rechazoPara.id}
          onClose={() => setRechazoPara(null)}
          onSuccess={() => { setRechazoPara(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function RowFirma({ doc, session, onView, onEscaneada, onRechazar, onChanged }) {
  const firmar = useFirmarDocumento(session);

  async function handleFirmar() {
    try {
      await firmar.submit(doc.documento_id || doc.id, {});
      onChanged?.();
    } catch { /* hook */ }
  }

  return (
    <tr data-testid="firmar-row">
      <td>
        <button
          type="button"
          className="link-as-button"
          onClick={onView}
          data-testid="firmar-row-link"
        >{doc.titulo || doc.documento_titulo || '(sin título)'}</button>
      </td>
      <td>{doc.tipo || '—'}</td>
      <td>{doc.solicitante_nombre || '—'}</td>
      <td>{fmtFecha(doc.solicitado_en)}</td>
      <td>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            className="btn btn-accent btn-sm"
            disabled={firmar.submitting}
            onClick={handleFirmar}
            data-testid="firmar-btn-digital"
          >{firmar.submitting ? 'Firmando…' : 'Firmar'}</button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onEscaneada}
            data-testid="firmar-btn-escaneada"
          >Escaneada</button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={onRechazar}
            data-testid="firmar-btn-rechazar"
          >Rechazar</button>
        </div>
      </td>
    </tr>
  );
}

function RechazoModal({ session, documentoId, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useRechazarFirmaDocumento(session);

  async function handle() {
    try {
      await hook.submit(documentoId, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" data-testid="firmar-rechazo-modal">
      <div className="modal-panel" style={{ maxWidth: 480 }}>
        <header className="modal-head">
          <h2>Rechazar firma</h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className="modal-body">
          <p className="muted" style={{ fontSize: 13 }}>
            El documento volverá al solicitante con el motivo de rechazo.
          </p>
          <JustificacionRequiredField
            value={motivo}
            onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
            label="Motivo del rechazo"
            id="firmar-rechazo-motivo"
          />
          {hook.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{hook.error.message || 'Error.'}</div>
            </div>
          )}
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="btn btn-danger-solid"
            disabled={!valid || hook.submitting}
            onClick={handle}
            data-testid="firmar-rechazo-submit"
          >{hook.submitting ? 'Enviando…' : 'Rechazar'}</button>
        </footer>
      </div>
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

export default PorFirmar;
