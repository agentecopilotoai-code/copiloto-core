/**
 * Impresion — GD-UI-0088/0089/0090.
 *
 * Imprimir etiqueta + constancia + cola de trabajos + reimprimir
 * con motivo. Embebido en RadicadoFicha también, pero esta es la
 * página standalone de "Centro de impresión".
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePerifericos, useTrabajosImpresion,
  useImprimirEtiqueta, useImprimirConstancia, useReimprimir,
} from './useGdPerifericos.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const FORMATOS_ETIQUETA = [
  { v: 'estandar', l: 'Estándar (50x30mm)' },
  { v: 'doble', l: 'Doble (100x60mm)' },
  { v: 'con_qr', l: 'Estándar con QR' },
];

export function Impresion({ session, roles = [], ...shellProps }) {
  const [tab, setTab] = useState('Imprimir');
  const puedeImprimir = gdCanAny(roles, 'PER-003', 'RW') || gdCanAny(roles, 'PER-005', 'RW');
  const puedeReimprimir = gdCanAny(roles, 'PER-004', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Centro de impresión' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Centro de impresión</h1>
          <p className="subtitle">
            Imprimir etiquetas y constancias de radicación, ver cola de
            trabajos, reimprimir.
          </p>
        </div>
      </div>

      {!puedeImprimir && (
        <div className="alert warning" role="alert" data-testid="imp-no-perm">
          <div className="body">No tiene permisos para imprimir.</div>
        </div>
      )}

      {puedeImprimir && (
        <>
          <nav className="tabs" data-testid="imp-tabs" role="tablist">
            {['Imprimir', 'Cola'].map((t) => (
              <button
                key={t} role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`imp-tab-btn-${t}`}
              >{t}</button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'Imprimir' && (
              <FormImprimir session={session} roles={roles} />
            )}
            {tab === 'Cola' && (
              <ColaTrabajos session={session} puedeReimprimir={puedeReimprimir} />
            )}
          </div>
        </>
      )}
    </GdShell>
  );
}

function FormImprimir({ session, roles }) {
  const [tipo, setTipo] = useState('etiqueta');
  const [radicadoId, setRadicadoId] = useState('');
  const [formato, setFormato] = useState('estandar');
  const [perifericoId, setPerifericoId] = useState('');
  const [copias, setCopias] = useState(1);
  const [info, setInfo] = useState(null);

  const perifericos = usePerifericos(session, {
    tipo: tipo === 'etiqueta' || tipo === 'constancia' ? 'impresora' : undefined,
    estado: 'activo',
  });
  const eti = useImprimirEtiqueta(session);
  const cons = useImprimirConstancia(session);
  const hook = tipo === 'etiqueta' ? eti : cons;

  async function handle() {
    setInfo(null);
    try {
      const r = await hook.submit({
        radicado_id: radicadoId,
        periferico_id: perifericoId,
        formato: tipo === 'etiqueta' ? formato : undefined,
        copias: Number(copias),
      });
      setInfo({ ok: true, ...r });
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  const puede = (tipo === 'etiqueta'
    ? gdCanAny(roles, 'PER-003', 'RW')
    : gdCanAny(roles, 'PER-005', 'RW'));

  const valid = radicadoId.trim() && perifericoId && copias > 0;

  return (
    <div data-testid="imp-form">
      <div className="field">
        <label>Tipo</label>
        <select className="select"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
          data-testid="imp-tipo"
        >
          <option value="etiqueta">Etiqueta de radicado</option>
          <option value="constancia">Constancia de radicación</option>
        </select>
      </div>

      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Número o UUID del radicado <span className="req">*</span></label>
        <input className="input" value={radicadoId}
          onChange={(e) => setRadicadoId(e.target.value)}
          data-testid="imp-radicado"
        />
      </div>

      {tipo === 'etiqueta' && (
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Formato de etiqueta</label>
          <select className="select"
            value={formato}
            onChange={(e) => setFormato(e.target.value)}
            data-testid="imp-formato"
          >
            {FORMATOS_ETIQUETA.map((f) => (
              <option key={f.v} value={f.v}>{f.l}</option>
            ))}
          </select>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginTop: 'var(--s-3)' }}>
        <div className="field">
          <label>Impresora <span className="req">*</span></label>
          <select className="select"
            value={perifericoId}
            onChange={(e) => setPerifericoId(e.target.value)}
            data-testid="imp-impresora"
          >
            <option value="">— Seleccione —</option>
            {perifericos.items.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.en_linea}>
                {p.codigo} — {p.ubicacion || p.modelo}
                {!p.en_linea && ' (fuera de línea)'}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Copias</label>
          <input type="number" min={1} max={10} className="input"
            value={copias}
            onChange={(e) => setCopias(e.target.value)}
            data-testid="imp-copias"
          />
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="imp-no-perm-tipo" style={{ marginTop: 12 }}>
          <div className="body">No tiene permisos para imprimir este tipo.</div>
        </div>
      )}

      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status" data-testid="imp-info" style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok
              ? <>Trabajo encolado (id <code>{info.trabajo_id || info.id || '—'}</code>).</>
              : <>Error: {info.error?.message || 'desconocido'}.</>
            }
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || !puede || hook.submitting}
          onClick={handle}
          data-testid="imp-submit"
        >{hook.submitting ? 'Imprimiendo…' : 'Imprimir'}</button>
      </div>
    </div>
  );
}

function ColaTrabajos({ session, puedeReimprimir }) {
  const { items, loading, error, refresh } = useTrabajosImpresion(session);
  const [reimp, setReimp] = useState(null);

  return (
    <div data-testid="imp-cola">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--s-3)' }}>
        <span className="muted" style={{ fontSize: 13 }}>
          {items.length} trabajo(s) en cola/recientes.
        </span>
        <button type="button" className="btn btn-secondary btn-sm"
          onClick={refresh}
          data-testid="imp-cola-refresh"
        >Actualizar</button>
      </div>
      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="imp-cola-empty">
          <p>No hay trabajos de impresión recientes.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="imp-cola-table">
          <thead>
            <tr>
              <th>Trabajo</th>
              <th>Tipo</th>
              <th>Radicado</th>
              <th>Impresora</th>
              <th>Estado</th>
              <th>Encolado</th>
              {puedeReimprimir && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} data-testid="imp-cola-row">
                <td><code>{t.id?.slice(0, 8)}</code></td>
                <td>{t.tipo}</td>
                <td>{t.numero_radicado || t.radicado_id?.slice(0, 8)}</td>
                <td>{t.periferico_codigo || '—'}</td>
                <td>
                  <span className={`badge ${badgeEstadoTrabajo(t.estado)}`}>
                    {t.estado}
                  </span>
                </td>
                <td>{fmt(t.creado_en)}</td>
                {puedeReimprimir && (
                  <td>
                    {(t.estado === 'completado' || t.estado === 'fallido') && (
                      <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => setReimp(t)}
                        data-testid="imp-reimprimir"
                      >Reimprimir</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {reimp && (
        <ReimprimirModal
          session={session} trabajo={reimp}
          onClose={() => setReimp(null)}
          onSuccess={() => { setReimp(null); refresh(); }}
        />
      )}
    </div>
  );
}

function ReimprimirModal({ session, trabajo, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useReimprimir(session);

  async function handle() {
    try {
      await hook.submit(trabajo.id, motivo);
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <div role="dialog" aria-modal="true" data-testid="imp-reimp-modal"
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 500, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Reimprimir trabajo</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Tipo: <strong>{trabajo.tipo}</strong> · Radicado{' '}
          {trabajo.numero_radicado || trabajo.radicado_id}. La reimpresión
          requiere motivo auditable.
        </p>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo de reimpresión"
          id="imp-reimp-motivo"
        />
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-accent"
            disabled={!valid || hook.submitting} onClick={handle}
            data-testid="imp-reimp-submit"
          >{hook.submitting ? 'Encolando…' : 'Reimprimir'}</button>
        </div>
      </div>
    </div>
  );
}

function badgeEstadoTrabajo(e) {
  if (e === 'completado') return 'ok';
  if (e === 'fallido') return 'danger';
  if (e === 'en_progreso') return 'info';
  return 'warn';
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default Impresion;
