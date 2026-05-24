/**
 * Digitalizacion — GD-UI-0091/0092/0093/0094.
 *
 * Centro de digitalización con 3 tabs:
 *  - Individual: escanear un documento y asociarlo a un radicado abierto.
 *  - Lote: enviar trabajo de digitalización masiva al escáner (cola).
 *  - Asociar: asociar una digitalización previa a un radicado
 *    (incluso radicados cerrados — PER-008 con motivo) +
 *    reemplazar una digitalización por otra (PER-009 con motivo).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePerifericos, useColaDigitalizacion,
  useDigitalizarIndividual, useDigitalizarLote,
  useAsociarDigitalizacionARadicado, useReemplazarDigitalizacion,
} from './useGdPerifericos.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['Individual', 'Lote', 'Asociar / reemplazar'];

export function Digitalizacion({ session, roles = [], ...shellProps }) {
  const [tab, setTab] = useState('Individual');
  const puedeIndividual = gdCanAny(roles, 'PER-006', 'RW');
  const puedeLote = gdCanAny(roles, 'PER-007', 'RW');
  const puedeAsociar = gdCanAny(roles, 'PER-008', 'RW')
    || gdCanAny(roles, 'PER-009', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Digitalización' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Centro de digitalización</h1>
          <p className="subtitle">
            Escaneo individual, lote y asociación posterior con
            radicados (con motivo si aplica).
          </p>
        </div>
      </div>

      {!puedeIndividual && !puedeLote && !puedeAsociar && (
        <div className="alert warning" role="alert" data-testid="dig-no-perm">
          <div className="body">No tiene permisos para digitalizar.</div>
        </div>
      )}

      {(puedeIndividual || puedeLote || puedeAsociar) && (
        <>
          <nav className="tabs" data-testid="dig-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t} role="tab"
                aria-selected={tab === t}
                className={`tab ${tab === t ? 'active' : ''}`}
                onClick={() => setTab(t)}
                data-testid={`dig-tab-btn-${t}`}
              >{t}</button>
            ))}
          </nav>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            {tab === 'Individual' && puedeIndividual && <FormIndividual session={session} />}
            {tab === 'Individual' && !puedeIndividual && <SinPerm tipo="individual" />}
            {tab === 'Lote' && puedeLote && <FormLote session={session} />}
            {tab === 'Lote' && !puedeLote && <SinPerm tipo="lote" />}
            {tab === 'Asociar / reemplazar' && puedeAsociar && (
              <PanelAsociar session={session} roles={roles} />
            )}
            {tab === 'Asociar / reemplazar' && !puedeAsociar && (
              <SinPerm tipo="asociar/reemplazar" />
            )}
          </div>
        </>
      )}
    </GdShell>
  );
}

function SinPerm({ tipo }) {
  return (
    <p className="muted" data-testid={`dig-no-perm-${tipo}`}>
      No tiene permisos para {tipo}.
    </p>
  );
}

function FormIndividual({ session }) {
  const escaneres = usePerifericos(session, { tipo: 'escaner', estado: 'activo' });
  const [form, setForm] = useState({
    periferico_id: '', radicado_id: '',
    dpi: 300, color: 'gris', formato: 'pdf',
  });
  const [info, setInfo] = useState(null);
  const hook = useDigitalizarIndividual(session);

  async function handle() {
    setInfo(null);
    try {
      const r = await hook.submit(form);
      setInfo({ ok: true, ...r });
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  const valid = form.periferico_id && form.radicado_id.trim();

  return (
    <div data-testid="dig-ind-form">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Digitalización individual</h3>
      <div className="field">
        <label>Escáner <span className="req">*</span></label>
        <select className="select"
          value={form.periferico_id}
          onChange={(e) => setForm({ ...form, periferico_id: e.target.value })}
          data-testid="dig-ind-escaner"
        >
          <option value="">— Seleccione —</option>
          {escaneres.items.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.en_linea}>
              {p.codigo} — {p.ubicacion || p.modelo}
              {!p.en_linea && ' (fuera de línea)'}
            </option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Número o UUID del radicado <span className="req">*</span></label>
        <input className="input"
          value={form.radicado_id}
          onChange={(e) => setForm({ ...form, radicado_id: e.target.value })}
          data-testid="dig-ind-radicado"
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginTop: 'var(--s-3)' }}>
        <div className="field">
          <label>DPI</label>
          <select className="select" value={form.dpi}
            onChange={(e) => setForm({ ...form, dpi: Number(e.target.value) })}
            data-testid="dig-ind-dpi"
          >
            <option value={200}>200</option>
            <option value={300}>300</option>
            <option value={600}>600</option>
          </select>
        </div>
        <div className="field">
          <label>Color</label>
          <select className="select" value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value })}
            data-testid="dig-ind-color"
          >
            <option value="bw">Blanco y negro</option>
            <option value="gris">Escala de grises</option>
            <option value="color">Color</option>
          </select>
        </div>
        <div className="field">
          <label>Formato</label>
          <select className="select" value={form.formato}
            onChange={(e) => setForm({ ...form, formato: e.target.value })}
            data-testid="dig-ind-formato"
          >
            <option value="pdf">PDF</option>
            <option value="tiff">TIFF</option>
            <option value="jpg">JPG</option>
          </select>
        </div>
      </div>

      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status" data-testid="dig-ind-info" style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok
              ? <>Digitalización encolada (id <code>{info.id || info.trabajo_id || '—'}</code>).</>
              : <>Error: {info.error?.message || 'desconocido'}.</>
            }
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="dig-ind-submit"
        >{hook.submitting ? 'Digitalizando…' : 'Digitalizar'}</button>
      </div>
    </div>
  );
}

function FormLote({ session }) {
  const escaneres = usePerifericos(session, { tipo: 'escaner', estado: 'activo' });
  const cola = useColaDigitalizacion(session);
  const [form, setForm] = useState({
    periferico_id: '', radicados_ids: '', dpi: 300, color: 'gris', formato: 'pdf',
  });
  const [info, setInfo] = useState(null);
  const hook = useDigitalizarLote(session);

  async function handle() {
    setInfo(null);
    try {
      const r = await hook.submit({
        ...form,
        radicados_ids: form.radicados_ids
          .split(/[,\n\r ]+/).map((s) => s.trim()).filter(Boolean),
      });
      setInfo({ ok: true, ...r });
      cola.refresh();
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  const cantidad = form.radicados_ids
    .split(/[,\n\r ]+/).map((s) => s.trim()).filter(Boolean).length;
  const valid = form.periferico_id && cantidad > 0;

  return (
    <div data-testid="dig-lote-form">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Digitalización por lote</h3>
      <div className="field">
        <label>Escáner <span className="req">*</span></label>
        <select className="select"
          value={form.periferico_id}
          onChange={(e) => setForm({ ...form, periferico_id: e.target.value })}
          data-testid="dig-lote-escaner"
        >
          <option value="">— Seleccione —</option>
          {escaneres.items.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.en_linea}>
              {p.codigo} — {p.ubicacion || p.modelo}
              {!p.en_linea && ' (fuera de línea)'}
            </option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Radicados (separados por coma, espacio o nueva línea)</label>
        <textarea className="textarea" rows={5}
          value={form.radicados_ids}
          onChange={(e) => setForm({ ...form, radicados_ids: e.target.value })}
          placeholder="2026-E-100, 2026-E-101, 2026-E-102"
          data-testid="dig-lote-radicados"
        />
        <p className="muted" style={{ fontSize: 11 }} data-testid="dig-lote-count">
          {cantidad} radicado(s) detectado(s).
        </p>
      </div>

      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status" data-testid="dig-lote-info" style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok
              ? <>Lote encolado ({cantidad} radicados, id <code>{info.id || info.lote_id || '—'}</code>).</>
              : <>Error: {info.error?.message || 'desconocido'}.</>
            }
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="dig-lote-submit"
        >{hook.submitting ? 'Encolando…' : 'Enviar lote a escáner'}</button>
      </div>

      <hr style={{ margin: 'var(--s-5) 0' }} />

      <h3 style={{ fontSize: 14 }}>Cola de digitalización</h3>
      {cola.loading && <p className="muted">Cargando cola…</p>}
      {cola.error && (
        <div className="alert danger" role="alert">
          <div className="body">{cola.error.message || 'Error.'}</div>
        </div>
      )}
      {!cola.loading && !cola.error && cola.items.length === 0 && (
        <div className="empty" data-testid="dig-cola-empty">
          <p>No hay trabajos de digitalización en cola.</p>
        </div>
      )}
      {cola.items.length > 0 && (
        <table className="data-table" data-testid="dig-cola-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tipo</th>
              <th>Cantidad</th>
              <th>Escáner</th>
              <th>Estado</th>
              <th>Encolado</th>
            </tr>
          </thead>
          <tbody>
            {cola.items.map((t) => (
              <tr key={t.id} data-testid="dig-cola-row">
                <td><code>{t.id?.slice(0, 8)}</code></td>
                <td>{t.tipo || (t.cantidad > 1 ? 'lote' : 'individual')}</td>
                <td className="num">{t.cantidad ?? 1}</td>
                <td>{t.periferico_codigo || '—'}</td>
                <td>
                  <span className={`badge ${badgeEstado(t.estado)}`}>{t.estado}</span>
                </td>
                <td>{fmt(t.creado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PanelAsociar({ session, roles }) {
  const puedeAsociar = gdCanAny(roles, 'PER-008', 'RW');
  const puedeReemplazar = gdCanAny(roles, 'PER-009', 'RW');
  return (
    <div data-testid="dig-asoc-panel">
      <p className="muted" style={{ fontSize: 13 }}>
        Operaciones excepcionales sobre digitalizaciones existentes. Ambas
        requieren motivo auditable y dejan trazabilidad completa.
      </p>
      {puedeAsociar && <FormAsociar session={session} />}
      {puedeReemplazar && <FormReemplazar session={session} />}
    </div>
  );
}

function FormAsociar({ session }) {
  const [form, setForm] = useState({
    digitalizacion_id: '', radicado_id: '',
  });
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const [info, setInfo] = useState(null);
  const hook = useAsociarDigitalizacionARadicado(session);

  async function handle() {
    setInfo(null);
    try {
      const r = await hook.submit({ ...form, motivo });
      setInfo({ ok: true, ...r });
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  const valid = form.digitalizacion_id.trim()
    && form.radicado_id.trim()
    && motivoValid;

  return (
    <div className="card" style={{ padding: 'var(--s-4)', marginTop: 'var(--s-4)' }}
      data-testid="dig-asoc-form">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>
        Asociar digitalización existente a radicado
      </h3>
      <p className="muted" style={{ fontSize: 12 }}>
        Útil cuando se digitaliza primero (sin radicar) o cuando se
        asocia a un radicado cerrado.
      </p>
      <div className="field">
        <label>UUID de digitalización <span className="req">*</span></label>
        <input className="input"
          value={form.digitalizacion_id}
          onChange={(e) => setForm({ ...form, digitalizacion_id: e.target.value })}
          data-testid="dig-asoc-dig"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Número o UUID del radicado <span className="req">*</span></label>
        <input className="input"
          value={form.radicado_id}
          onChange={(e) => setForm({ ...form, radicado_id: e.target.value })}
          data-testid="dig-asoc-radicado"
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
          label="Motivo de la asociación"
          id="dig-asoc-motivo"
        />
      </div>
      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status" data-testid="dig-asoc-info" style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok
              ? <>Asociación registrada.</>
              : <>Error: {info.error?.message || 'desconocido'}.</>
            }
          </div>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="dig-asoc-submit"
        >{hook.submitting ? 'Asociando…' : 'Asociar'}</button>
      </div>
    </div>
  );
}

function FormReemplazar({ session }) {
  const [form, setForm] = useState({
    digitalizacion_id: '', nuevo_archivo_id: '',
  });
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const [info, setInfo] = useState(null);
  const hook = useReemplazarDigitalizacion(session);

  async function handle() {
    setInfo(null);
    try {
      const r = await hook.submit(form.digitalizacion_id, {
        nuevo_archivo_id: form.nuevo_archivo_id, motivo,
      });
      setInfo({ ok: true, ...r });
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  const valid = form.digitalizacion_id.trim()
    && form.nuevo_archivo_id.trim()
    && motivoValid;

  return (
    <div className="card" style={{ padding: 'var(--s-4)', marginTop: 'var(--s-4)' }}
      data-testid="dig-reemp-form">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>
        Reemplazar digitalización (PER-009)
      </h3>
      <p className="muted" style={{ fontSize: 12 }}>
        Solo Coordinador VU o Admin Sistema. La digitalización
        original NO se elimina — queda con marca "reemplazada" para
        auditoría.
      </p>
      <div className="field">
        <label>UUID de digitalización a reemplazar <span className="req">*</span></label>
        <input className="input"
          value={form.digitalizacion_id}
          onChange={(e) => setForm({ ...form, digitalizacion_id: e.target.value })}
          data-testid="dig-reemp-dig"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>UUID del nuevo archivo digital <span className="req">*</span></label>
        <input className="input"
          value={form.nuevo_archivo_id}
          onChange={(e) => setForm({ ...form, nuevo_archivo_id: e.target.value })}
          data-testid="dig-reemp-arch"
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
          label="Motivo del reemplazo"
          id="dig-reemp-motivo"
        />
      </div>
      {info && (
        <div className={`alert ${info.ok ? 'success' : 'danger'}`}
          role="status" data-testid="dig-reemp-info" style={{ marginTop: 12 }}
        >
          <div className="body">
            {info.ok
              ? <>Reemplazo registrado. Original marcada como reemplazada.</>
              : <>Error: {info.error?.message || 'desconocido'}.</>
            }
          </div>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="dig-reemp-submit"
        >{hook.submitting ? 'Reemplazando…' : 'Reemplazar'}</button>
      </div>
    </div>
  );
}

function badgeEstado(e) {
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

export default Digitalizacion;
