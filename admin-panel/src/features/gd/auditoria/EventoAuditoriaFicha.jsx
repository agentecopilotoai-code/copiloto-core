/**
 * EventoAuditoriaFicha — GD-UI-0068. Detalle de evento con diff.
 *
 * Muestra:
 *  - Datos generales (actor, fecha, IP, user-agent, hash)
 *  - Payload de la acción
 *  - Diff antes/después (objetos jsonificados con highlight básico)
 *  - Verificación de integridad del hash (botón a backend)
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useEventoAuditoria, useVerificarHashRegistro,
} from './useGdAuditoria.js';

export function EventoAuditoriaFicha({
  session, eventoId, ...shellProps
}) {
  const { data, loading, error } = useEventoAuditoria(session, eventoId);
  const verificar = useVerificarHashRegistro(session);
  const [verifInfo, setVerifInfo] = useState(null);

  async function handleVerificar() {
    if (!data) return;
    setVerifInfo(null);
    try {
      const r = await verificar.submit(data.entidad_tipo, data.entidad_id);
      setVerifInfo({ ok: r?.integro !== false, ...r });
    } catch (err) {
      setVerifInfo({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Auditoría', path: '/gd/auditoria' },
        { label: data?.id?.slice(0, 8) || 'Evento' },
      ]}
    >
      {loading && <p className="muted">Cargando evento…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <>
          <div className="page-head">
            <div className="title-block">
              <h1 style={{ fontSize: 18 }}>
                <span className="badge">{data.accion}</span>{' '}
                sobre {data.entidad_tipo}
              </h1>
              <p className="subtitle">
                Por <strong>{data.actor_email || data.actor_id}</strong> el{' '}
                {fmt(data.created_at || data.timestamp)}.
              </p>
            </div>
            <div className="actions">
              <button type="button" className="btn btn-secondary"
                disabled={verificar.submitting}
                onClick={handleVerificar}
                data-testid="evt-verificar"
              >
                {verificar.submitting ? 'Verificando…' : 'Verificar integridad'}
              </button>
            </div>
          </div>

          {verifInfo && (
            <div
              className={`alert ${verifInfo.ok ? 'success' : 'danger'}`}
              role="status"
              data-testid="evt-verif-info"
              style={{ marginBottom: 'var(--s-3)' }}
            >
              <div className="body">
                {verifInfo.ok
                  ? <>Hash íntegro. El registro NO ha sido alterado desde su creación.</>
                  : <>⚠ Integridad comprometida o no verificable:{' '}
                      {verifInfo.error?.message || verifInfo.detalle || 'verificación fallida'}.</>
                }
              </div>
            </div>
          )}

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }} data-testid="evt-general">
            <h2 style={{ fontSize: 16, marginTop: 0 }}>Datos generales</h2>
            <Row label="ID evento" value={<code>{data.id}</code>} />
            <Row label="Actor" value={`${data.actor_email || ''} (${data.actor_id || '—'})`} />
            <Row label="Acción" value={data.accion} />
            <Row label="Entidad" value={`${data.entidad_tipo} / ${data.entidad_id || '—'}`} />
            <Row label="IP" value={data.ip || '—'} />
            <Row label="User-Agent" value={data.user_agent || '—'} />
            <Row label="Fecha" value={fmt(data.created_at || data.timestamp)} />
            <Row label="Hash SHA-256"
              value={<code data-testid="evt-hash">{data.hash || '—'}</code>} />
            {data.hash_prev && (
              <Row label="Hash registro previo"
                value={<code data-testid="evt-hash-prev">{data.hash_prev}</code>} />
            )}
          </div>

          {data.motivo && (
            <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Motivo / justificación</h3>
              <p data-testid="evt-motivo">{data.motivo}</p>
            </div>
          )}

          <div className="card" style={{ padding: 'var(--s-5)' }} data-testid="evt-diff">
            <h2 style={{ fontSize: 16, marginTop: 0 }}>Cambios</h2>
            <DiffView antes={data.payload_antes} despues={data.payload_despues} />
          </div>

          {data.payload && (
            <div className="card" style={{ padding: 'var(--s-5)', marginTop: 'var(--s-4)' }}>
              <h2 style={{ fontSize: 16, marginTop: 0 }}>Payload</h2>
              <pre
                data-testid="evt-payload"
                style={{
                  background: 'var(--surface-alt)',
                  padding: 'var(--s-3)', borderRadius: 'var(--r-md)',
                  fontSize: 12, overflow: 'auto', maxHeight: 320,
                }}
              >{JSON.stringify(data.payload, null, 2)}</pre>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

function DiffView({ antes, despues }) {
  if (!antes && !despues) {
    return <p className="muted">Sin diff (operación de solo-lectura).</p>;
  }
  const keys = new Set([
    ...Object.keys(antes || {}),
    ...Object.keys(despues || {}),
  ]);
  const changed = [];
  const unchanged = [];
  for (const k of keys) {
    const a = (antes || {})[k];
    const d = (despues || {})[k];
    const eq = JSON.stringify(a) === JSON.stringify(d);
    (eq ? unchanged : changed).push({ k, a, d });
  }
  if (changed.length === 0) {
    return <p className="muted" data-testid="evt-diff-nochange">No hay cambios entre antes y después.</p>;
  }
  return (
    <table className="data-table" data-testid="evt-diff-table">
      <thead>
        <tr>
          <th>Campo</th>
          <th>Antes</th>
          <th>Después</th>
        </tr>
      </thead>
      <tbody>
        {changed.map(({ k, a, d }) => (
          <tr key={k} data-testid="evt-diff-row">
            <td><code>{k}</code></td>
            <td style={{ background: 'var(--red-50)', color: 'var(--red-700)' }}>
              <code>{fmtVal(a)}</code>
            </td>
            <td style={{ background: 'var(--green-50)', color: 'var(--green-700)' }}>
              <code>{fmtVal(d)}</code>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function fmtVal(v) {
  if (v === undefined) return '∅';
  if (v === null) return 'null';
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 80);
  return String(v).slice(0, 80);
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

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default EventoAuditoriaFicha;
