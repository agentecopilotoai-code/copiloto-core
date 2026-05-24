/**
 * CorreoImportado — GD-UI-0079/0080/0081.
 *
 * Bandeja de correos institucionales importados (vía IMAP / inbound
 * webhook). Permite:
 *  - Convertir un correo en radicado (consumiendo metadatos automáticos)
 *  - Descartar como spam o duplicado (con motivo auditable)
 *  - Ver detalle del correo (remitente, asunto, cuerpo, adjuntos)
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useCorreosImportados, useCorreoImportado,
  useConvertirCorreoARadicado, useDescartarCorreo,
} from './useGdComunicaciones.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const ESTADOS = ['', 'pendiente', 'convertido', 'descartado'];

export function CorreoImportado({ session, roles = [], ...shellProps }) {
  const [filtros, setFiltros] = useState({ estado: 'pendiente' });
  const { items, total, loading, error, refresh } =
    useCorreosImportados(session, filtros);
  const [selId, setSelId] = useState(null);
  const [modal, setModal] = useState(null);
  const detalle = useCorreoImportado(session, selId, { enabled: !!selId });
  const puede = gdCanAny(roles, 'COR-IN-001', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Correo importado' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Correo institucional importado</h1>
          <p className="subtitle">
            {total} correo(s) — bandeja de entrada del buzón institucional.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="cor-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="cor-no-perm">
          <div className="body">No tiene permisos para gestionar correo importado.</div>
        </div>
      )}

      {puede && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--s-3)' }}>
              <div className="field">
                <label>Búsqueda</label>
                <input type="search" className="input"
                  value={filtros.q || ''}
                  onChange={(e) => update('q', e.target.value)}
                  placeholder="Asunto o remitente…"
                  data-testid="cor-filter-q"
                />
              </div>
              <div className="field">
                <label>Estado</label>
                <select className="select"
                  value={filtros.estado || ''}
                  onChange={(e) => update('estado', e.target.value)}
                  data-testid="cor-filter-estado"
                >
                  {ESTADOS.map((e) => (
                    <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div data-testid="cor-layout"
            style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 'var(--s-4)' }}>
            <aside className="card" style={{ padding: 0, maxHeight: '70vh', overflow: 'auto' }}>
              {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
              {error && (
                <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
                  <div className="body">{error.message || 'Error.'}</div>
                </div>
              )}
              {!loading && !error && items.length === 0 && (
                <div className="empty" data-testid="cor-empty"
                  style={{ padding: 'var(--s-4)' }}>
                  <p>No hay correos con esos criterios.</p>
                </div>
              )}
              {items.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  data-testid="cor-row"
                  onClick={() => setSelId(c.id)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: 'var(--s-3)',
                    border: 0,
                    borderBottom: '1px solid var(--border-subtle)',
                    background: selId === c.id ? 'var(--sky-50)' : 'transparent',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontWeight: c.leido ? 400 : 700, fontSize: 13 }}>
                    {c.asunto}
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {c.remitente} · {fmt(c.recibido_en)}
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <span className={`badge ${badgeEstado(c.estado)}`} style={{ fontSize: 10 }}>
                      {c.estado}
                    </span>
                  </div>
                </button>
              ))}
            </aside>

            <section className="card" style={{ padding: 'var(--s-5)' }}>
              {!selId && (
                <p className="muted" data-testid="cor-vacio">
                  Seleccione un correo para ver el detalle.
                </p>
              )}
              {selId && detalle.loading && <p className="muted">Cargando detalle…</p>}
              {selId && detalle.error && (
                <div className="alert danger" role="alert">
                  <div className="body">{detalle.error.message || 'Error.'}</div>
                </div>
              )}
              {selId && detalle.data && (
                <DetalleCorreo
                  correo={detalle.data}
                  onConvertir={() => setModal({ tipo: 'convertir' })}
                  onDescartar={() => setModal({ tipo: 'descartar' })}
                />
              )}
            </section>
          </div>
        </>
      )}

      {modal?.tipo === 'convertir' && selId && (
        <ConvertirCorreoModal
          session={session} correoId={selId}
          correo={detalle.data}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); detalle.refresh(); }}
        />
      )}
      {modal?.tipo === 'descartar' && selId && (
        <DescartarCorreoModal
          session={session} correoId={selId}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); detalle.refresh(); }}
        />
      )}
    </GdShell>
  );
}

function DetalleCorreo({ correo, onConvertir, onDescartar }) {
  const editable = correo.estado === 'pendiente';
  return (
    <div data-testid="cor-detalle">
      <h2 style={{ marginTop: 0, fontSize: 17 }}>{correo.asunto}</h2>
      <p className="muted" style={{ fontSize: 12 }}>
        <strong>De:</strong> {correo.remitente}
        {' '}· <strong>Para:</strong> {correo.destinatario}
        {' '}· {fmt(correo.recibido_en)}
      </p>
      <div style={{
        background: 'var(--surface-alt)',
        padding: 'var(--s-4)',
        borderRadius: 'var(--r-md)',
        whiteSpace: 'pre-wrap',
        fontSize: 13,
        lineHeight: 1.55,
        marginTop: 'var(--s-3)',
      }} data-testid="cor-cuerpo">
        {correo.cuerpo || '(sin cuerpo)'}
      </div>
      {(correo.adjuntos || []).length > 0 && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <div className="muted" style={{ fontSize: 12 }}>Adjuntos</div>
          <ul data-testid="cor-adjuntos" style={{ margin: 0, paddingLeft: 16, fontSize: 13 }}>
            {correo.adjuntos.map((a, i) => (
              <li key={i}>
                {a.url ? <a href={a.url}>{a.nombre}</a> : a.nombre}
                {' '}<span className="muted">({a.size_kb} KB)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-accent"
            onClick={onConvertir}
            data-testid="cor-convertir"
          >Convertir en radicado</button>
          <button type="button" className="btn btn-danger"
            onClick={onDescartar}
            data-testid="cor-descartar"
          >Descartar</button>
        </div>
      )}
    </div>
  );
}

function ConvertirCorreoModal({ session, correoId, correo, onClose, onSuccess }) {
  const [form, setForm] = useState({
    asunto: correo?.asunto || '',
    canal: 'email',
    tercero_email: correo?.remitente || '',
  });
  const hook = useConvertirCorreoARadicado(session);

  async function handle() {
    try {
      await hook.submit(correoId, form);
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Convertir correo en radicado" onClose={onClose} testid="cor-convertir-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        Se generará un radicado de entrada con los metadatos del correo.
        Los adjuntos se incorporarán como anexos.
      </p>
      <div className="field">
        <label>Asunto del radicado</label>
        <input className="input" value={form.asunto}
          onChange={(e) => setForm({ ...form, asunto: e.target.value })}
          data-testid="cor-conv-asunto"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Correo del remitente</label>
        <input className="input" value={form.tercero_email}
          onChange={(e) => setForm({ ...form, tercero_email: e.target.value })}
          data-testid="cor-conv-email"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={hook.submitting} onClick={handle}
          data-testid="cor-conv-submit"
        >{hook.submitting ? 'Radicando…' : 'Convertir'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function DescartarCorreoModal({ session, correoId, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useDescartarCorreo(session);

  async function handle() {
    try {
      await hook.submit(correoId, motivo);
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Descartar correo" onClose={onClose} testid="cor-descartar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        El correo se marcará como descartado (spam, duplicado o no
        institucional). Permanece en la bitácora para auditoría.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo del descarte"
        id="cor-descartar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="cor-descartar-submit"
        >{hook.submitting ? 'Descartando…' : 'Descartar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div role="dialog" aria-modal="true" data-testid={testid}
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 500, padding: 'var(--s-5)' }}>
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

function badgeEstado(e) {
  if (e === 'convertido') return 'ok';
  if (e === 'descartado') return 'danger';
  return 'info';
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default CorreoImportado;
