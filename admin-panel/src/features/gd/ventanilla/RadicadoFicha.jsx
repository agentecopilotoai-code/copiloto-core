/**
 * RadicadoFicha — GD-UI-0015. Ficha completa de un radicado con 5 tabs.
 *
 * Tabs:
 *  - General: número, fecha, canal, estado, asunto, descripción, tercero.
 *  - Anexos: archivos adjuntos con descarga auditada.
 *  - Clasificación: clasificación actual + historial (versiones anteriores
 *    cuando hubo reclasificación — GD-API-0027).
 *  - Trazabilidad: <WorkflowTimeline /> consumiendo useGdAudit.
 *  - Acciones: gated por permisos (solicitar anulación, reclasificar,
 *    corrección menor, imprimir constancia).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { WorkflowTimeline } from '../components/WorkflowTimeline.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { RadicadoConstanciaPreview } from './RadicadoConstanciaPreview.jsx';
import {
  useGdRadicado,
  useReclasificarRadicado,
  useCorregirDatosMenores,
  useSolicitarAnulacion,
} from './useGdRadicados.js';
import { useGdAudit } from '../hooks/useGdAudit.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['General', 'Anexos', 'Clasificación', 'Trazabilidad', 'Acciones'];

const TIPOS_CLASIF = [
  { value: 'pqrsd', label: 'PQRSD' },
  { value: 'correspondencia_externa', label: 'Correspondencia externa' },
  { value: 'tramite', label: 'Trámite' },
  { value: 'expediente', label: 'Expediente' },
];

export function RadicadoFicha({
  session,
  radicadoId,
  roles = [],
  entidad,
  onNavigate,
  ...shellProps
}) {
  const [tab, setTab] = useState('General');
  const [modal, setModal] = useState(null); // 'reclasif' | 'datos' | 'anular' | null

  const { data: rad, loading, error, refresh } = useGdRadicado(session, radicadoId);
  const { events, loading: audLoading, error: audError } = useGdAudit({
    session,
    entidadTipo: 'radicado',
    entidadId: radicadoId,
    enabled: tab === 'Trazabilidad',
  });

  const reclasif = useReclasificarRadicado(session);
  const corregir = useCorregirDatosMenores(session);
  const anular = useSolicitarAnulacion(session);

  const puedeReclasificar = gdCanAny(roles, 'VU-006', 'RW');
  const puedeCorregir = gdCanAny(roles, 'VU-014', 'RW');
  const puedeAnular = gdCanAny(roles, 'VU-015', 'RW');

  return (
    <GdShell
      {...shellProps}
      roles={roles}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: rad?.numero_radicado || 'Radicado' },
      ]}
    >
      {loading && <p className="muted">Cargando radicado…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">
            <div className="title">No se pudo cargar el radicado.</div>
            <div>{error.message || 'Verifique el código o intente luego.'}</div>
          </div>
        </div>
      )}

      {rad && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontFamily: 'var(--font-mono)', fontSize: 22 }}>
                {rad.numero_radicado}
              </h1>
              <p className="subtitle">
                {rad.asunto}
              </p>
            </div>
            <div className="actions">
              {puedeAnular && rad.estado !== 'anulado' && (
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => setModal('anular')}
                  data-testid="btn-anular"
                >
                  Solicitar anulación
                </button>
              )}
              {puedeReclasificar && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setModal('reclasif')}
                  data-testid="btn-reclasificar"
                >
                  Reclasificar
                </button>
              )}
              {puedeCorregir && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setModal('datos')}
                  data-testid="btn-corregir"
                >
                  Corregir datos
                </button>
              )}
            </div>
          </div>

          <nav className="tabs" data-testid="ficha-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`tab-${t}`}
              >
                {t}
              </button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)', marginTop: 0 }}>
            {tab === 'General' && <TabGeneral rad={rad} />}
            {tab === 'Anexos' && <TabAnexos rad={rad} />}
            {tab === 'Clasificación' && <TabClasificacion rad={rad} />}
            {tab === 'Trazabilidad' && (
              <WorkflowTimeline
                events={events}
                loading={audLoading}
                error={audError}
              />
            )}
            {tab === 'Acciones' && (
              <TabAcciones
                rad={rad}
                entidad={entidad}
                puedeAnular={puedeAnular}
                puedeReclasificar={puedeReclasificar}
                puedeCorregir={puedeCorregir}
                onOpenModal={setModal}
              />
            )}
          </div>

          {modal === 'reclasif' && (
            <ReclasifModal
              hook={reclasif}
              radicadoId={radicadoId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
          {modal === 'datos' && (
            <CorregirModal
              hook={corregir}
              radicado={rad}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
          {modal === 'anular' && (
            <AnularModal
              hook={anular}
              radicadoId={radicadoId}
              onClose={() => setModal(null)}
              onSuccess={() => { setModal(null); refresh(); }}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

function TabGeneral({ rad }) {
  return (
    <div data-testid="tab-content-General">
      <Row label="Número" value={rad.numero_radicado} mono />
      <Row label="Tipo" value={rad.tipo_radicado} />
      <Row label="Estado" value={rad.estado} />
      <Row label="Canal" value={rad.canal_nombre || '—'} />
      <Row label="Fecha de radicación" value={fmtFecha(rad.fecha_radicacion)} />
      <Row label="Dependencia actual" value={rad.dependencia_actual_nombre || '—'} />
      <Row label="Asunto" value={rad.asunto} />
      {rad.descripcion && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Descripción</div>
          <p style={{ margin: 0 }}>{rad.descripcion}</p>
        </div>
      )}
    </div>
  );
}

function TabAnexos({ rad }) {
  const anexos = rad.anexos || [];
  if (anexos.length === 0) {
    return (
      <div className="empty" data-testid="anexos-empty">
        <p className="muted">Este radicado no tiene anexos registrados.</p>
      </div>
    );
  }
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }} data-testid="anexos-list">
      {anexos.map((a) => (
        <li
          key={a.id}
          style={{
            display: 'flex', alignItems: 'center', gap: 'var(--s-3)',
            padding: 'var(--s-3) 0',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <span style={{ flex: 1 }}>📎 {a.nombre}</span>
          <span className="muted" style={{ fontSize: 12 }}>
            {a.mime_type || '—'} · {a.size ? `${Math.round(a.size / 1024)} KB` : '—'}
          </span>
          <a
            href={a.url || '#'}
            className="btn btn-sm btn-secondary"
            data-testid="anexo-descargar"
          >
            Descargar
          </a>
        </li>
      ))}
    </ul>
  );
}

function TabClasificacion({ rad }) {
  const actual = rad.clasificacion_actual;
  const historial = rad.clasificacion_historial || [];
  return (
    <div data-testid="tab-content-Clasificación">
      {actual ? (
        <div className="alert info" style={{ marginBottom: 'var(--s-4)' }}>
          <div className="body">
            <div className="title">Clasificación actual</div>
            <div>
              <strong>{actual.tipo_clasificacion}</strong>
              {actual.sub_tipo && ` · ${actual.sub_tipo}`}
              {actual.dependencia_destino_nombre &&
                ` → ${actual.dependencia_destino_nombre}`}
            </div>
          </div>
        </div>
      ) : (
        <div className="empty">
          <p className="muted">Sin clasificación inicial.</p>
        </div>
      )}
      {historial.length > 0 && (
        <>
          <h3 style={{ fontSize: 14 }}>Versiones anteriores</h3>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {historial.map((h) => (
              <li
                key={h.id}
                style={{
                  padding: 'var(--s-2) 0',
                  borderBottom: '1px solid var(--border-subtle)',
                  fontSize: 13,
                }}
              >
                <span className="muted">{fmtFecha(h.fecha)} · {h.usuario_nombre}</span>
                <br />
                {h.tipo_clasificacion} {h.sub_tipo && `· ${h.sub_tipo}`}
                {h.justificacion && (
                  <span className="muted" style={{ fontStyle: 'italic' }}>
                    {' '}— «{h.justificacion}»
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function TabAcciones({ rad, entidad, puedeAnular, puedeReclasificar, puedeCorregir, onOpenModal }) {
  return (
    <div data-testid="tab-content-Acciones">
      <h3 style={{ fontSize: 14 }}>Acciones disponibles</h3>
      <div style={{ display: 'flex', gap: 'var(--s-2)', flexWrap: 'wrap', marginBottom: 'var(--s-5)' }}>
        {puedeReclasificar && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onOpenModal('reclasif')}
          >
            Reclasificar
          </button>
        )}
        {puedeCorregir && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onOpenModal('datos')}
          >
            Corregir datos menores
          </button>
        )}
        {puedeAnular && rad.estado !== 'anulado' && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => onOpenModal('anular')}
          >
            Solicitar anulación
          </button>
        )}
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => window.print && window.print()}
        >
          Imprimir constancia
        </button>
      </div>
      <h3 style={{ fontSize: 14, marginTop: 'var(--s-5)' }}>Constancia</h3>
      <RadicadoConstanciaPreview radicado={rad} entidad={entidad} />
    </div>
  );
}

/* ────────────── Modales reusables ────────────── */

function ModalShell({ title, children, onClose }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="ficha-modal"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(15, 23, 42, 0.4)',
        display: 'grid', placeItems: 'center',
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card"
        style={{ width: 480, padding: 'var(--s-5)' }}
      >
        <h2 style={{ margin: 0, fontSize: 16, marginBottom: 'var(--s-4)' }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ReclasifModal({ hook, radicadoId, onClose, onSuccess }) {
  const [tipo, setTipo] = useState('');
  const [subTipo, setSubTipo] = useState('');
  const [justif, setJustif] = useState('');
  const [valid, setValid] = useState(false);

  async function handle() {
    try {
      await hook.submit(radicadoId, {
        tipo_clasificacion: tipo,
        sub_tipo: subTipo || undefined,
        justificacion: justif,
      });
      onSuccess?.();
    } catch { /* error en hook */ }
  }

  return (
    <ModalShell title="Reclasificar radicado" onClose={onClose}>
      <div className="field">
        <label>Nuevo tipo <span className="req">*</span></label>
        <select
          className="select"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
          data-testid="modal-tipo"
        >
          <option value="">Seleccione…</option>
          {TIPOS_CLASIF.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Sub-tipo</label>
        <input
          className="input"
          value={subTipo}
          onChange={(e) => setSubTipo(e.target.value)}
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={justif}
          onChange={(v, ok) => { setJustif(v); setValid(ok); }}
          label="Justificación obligatoria"
          id="justif-reclasif"
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
          onClick={handle}
          disabled={!tipo || !valid || hook.submitting}
          data-testid="modal-reclasif-submit"
        >
          {hook.submitting ? 'Reclasificando…' : 'Reclasificar'}
        </button>
      </ModalFoot>
    </ModalShell>
  );
}

function CorregirModal({ hook, radicado, onClose, onSuccess }) {
  const [asunto, setAsunto] = useState(radicado.asunto || '');
  const [descripcion, setDescripcion] = useState(radicado.descripcion || '');
  const [justif, setJustif] = useState('');
  const [valid, setValid] = useState(false);

  async function handle() {
    try {
      await hook.submit(radicado.id, {
        asunto: asunto !== radicado.asunto ? asunto : undefined,
        descripcion: descripcion !== radicado.descripcion ? descripcion : undefined,
        justificacion: justif,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Corregir datos menores" onClose={onClose}>
      <div className="field">
        <label>Asunto</label>
        <input
          className="input"
          value={asunto}
          onChange={(e) => setAsunto(e.target.value)}
          data-testid="modal-corregir-asunto"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea
          className="textarea"
          rows={3}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={justif}
          onChange={(v, ok) => { setJustif(v); setValid(ok); }}
          id="justif-corregir"
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
          onClick={handle}
          disabled={!valid || hook.submitting}
          data-testid="modal-corregir-submit"
        >
          {hook.submitting ? 'Guardando…' : 'Guardar corrección'}
        </button>
      </ModalFoot>
    </ModalShell>
  );
}

function AnularModal({ hook, radicadoId, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);

  async function handle() {
    try {
      await hook.submit(radicadoId, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Solicitar anulación del radicado" onClose={onClose}>
      <p className="muted" style={{ fontSize: 13 }}>
        La anulación es irreversible y debe ser aprobada por el coordinador VU
        (RNF-058: solicitante ≠ aprobador). Indique el motivo con detalle.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de anulación"
        minLength={10}
        id="justif-anular"
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
          onClick={handle}
          disabled={!valid || hook.submitting}
          data-testid="modal-anular-submit"
        >
          {hook.submitting ? 'Solicitando…' : 'Solicitar anulación'}
        </button>
      </ModalFoot>
    </ModalShell>
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

function Row({ label, value, mono = false }) {
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
      <span style={{ fontFamily: mono ? 'var(--font-mono)' : undefined }}>
        {value || '—'}
      </span>
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

export default RadicadoFicha;
