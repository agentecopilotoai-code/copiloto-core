/**
 * DeteccionPII — GD-UI-0076. Detección de PII + alertas de privacidad.
 *
 * Ley 1581/2012 (datos personales). El sistema detecta automáticamente
 * cédulas, correos, teléfonos, direcciones, datos sensibles en
 * documentos cargados y emite alertas. IA-005.
 *
 * Vista: panel de alertas + utilitario "analizar texto inline".
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useAlertasPii, useDetectarPiiIA, useMarcarAlertaPiiAtendida,
} from './useGdIA.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const ESTADOS = ['', 'pendiente', 'atendida', 'falsa_alarma'];
const SEVERIDADES = ['baja', 'media', 'alta', 'critica'];

export function DeteccionPII({ session, roles = [], ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const { items, total, loading, error, refresh } =
    useAlertasPii(session, filtros);
  const [atender, setAtender] = useState(null);
  const [analizar, setAnalizar] = useState({ open: false, texto: '', resultado: null });
  const detectar = useDetectarPiiIA(session);
  const puede = gdCanAny(roles, 'IA-005', 'R');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  async function handleAnalizar() {
    try {
      const r = await detectar.submit({ texto: analizar.texto });
      setAnalizar((p) => ({ ...p, resultado: r }));
    } catch { /* */ }
  }

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Privacidad y PII' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Detección de PII y alertas de privacidad</h1>
          <p className="subtitle">
            Cumplimiento Ley 1581/2012. {total} alerta(s) en el filtro
            actual.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="ia-pii-refresh"
          >Actualizar</button>
          <button type="button" className="btn btn-accent"
            onClick={() => setAnalizar({ open: true, texto: '', resultado: null })}
            data-testid="ia-pii-analizar"
          >Analizar texto</button>
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="ia-pii-no-perm">
          <div className="body">No tiene permisos para ver alertas PII.</div>
        </div>
      )}

      {puede && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--s-3)' }}>
              <div className="field">
                <label>Estado</label>
                <select className="select"
                  value={filtros.estado || ''}
                  onChange={(e) => update('estado', e.target.value)}
                  data-testid="ia-pii-filter-estado"
                >
                  {ESTADOS.map((e) => (
                    <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Severidad mínima</label>
                <select className="select"
                  value={filtros.severidad || ''}
                  onChange={(e) => update('severidad', e.target.value)}
                  data-testid="ia-pii-filter-sev"
                >
                  <option value="">Cualquiera</option>
                  {SEVERIDADES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
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
              <div className="empty" data-testid="ia-pii-empty" style={{ margin: 'var(--s-4)' }}>
                <p>Sin alertas de PII con esos criterios.</p>
              </div>
            )}
            {items.length > 0 && (
              <table className="data-table" data-testid="ia-pii-table">
                <thead>
                  <tr>
                    <th>Severidad</th>
                    <th>Tipos detectados</th>
                    <th>Documento</th>
                    <th>Detectada</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((a) => (
                    <tr key={a.id} data-testid="ia-pii-row">
                      <td>
                        <span className={`badge ${badgeSev(a.severidad)}`}>{a.severidad}</span>
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {(a.tipos || []).join(', ')}
                      </td>
                      <td>{a.documento_titulo || a.documento_id?.slice(0, 8) || '—'}</td>
                      <td>{fmt(a.detectada_en)}</td>
                      <td>
                        <span className={`badge ${a.estado === 'pendiente' ? 'warn' : 'neutral'}`}>
                          {a.estado}
                        </span>
                      </td>
                      <td>
                        {a.estado === 'pendiente' && (
                          <button type="button" className="btn btn-secondary btn-sm"
                            onClick={() => setAtender(a)}
                            data-testid="ia-pii-atender"
                          >Atender</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {atender && (
        <AtenderAlertaModal
          session={session} alerta={atender}
          onClose={() => setAtender(null)}
          onSuccess={() => { setAtender(null); refresh(); }}
        />
      )}

      {analizar.open && (
        <AnalizarTextoModal
          texto={analizar.texto}
          resultado={analizar.resultado}
          submitting={detectar.submitting}
          error={detectar.error}
          onTexto={(t) => setAnalizar((p) => ({ ...p, texto: t }))}
          onAnalizar={handleAnalizar}
          onClose={() => setAnalizar({ open: false, texto: '', resultado: null })}
        />
      )}
    </GdShell>
  );
}

function AtenderAlertaModal({ session, alerta, onClose, onSuccess }) {
  const [decision, setDecision] = useState('atendida');
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useMarcarAlertaPiiAtendida(session);

  async function handle() {
    try {
      await hook.submit(alerta.id, { decision, motivo });
      onSuccess?.();
    } catch { /* */ }
  }

  return (
    <ModalShell title="Atender alerta PII" onClose={onClose} testid="ia-pii-atender-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        Tipos detectados: <strong>{(alerta.tipos || []).join(', ')}</strong>.
        Documento: {alerta.documento_titulo || alerta.documento_id}.
      </p>
      <div className="field">
        <label>Decisión</label>
        <select className="select"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          data-testid="ia-pii-atender-decision"
        >
          <option value="atendida">Atender (datos enmascarados/eliminados)</option>
          <option value="falsa_alarma">Falsa alarma</option>
        </select>
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Acción tomada / justificación"
          id="ia-pii-motivo"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="ia-pii-atender-submit"
        >{hook.submitting ? 'Guardando…' : 'Marcar como atendida'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function AnalizarTextoModal({ texto, resultado, submitting, error, onTexto, onAnalizar, onClose }) {
  return (
    <ModalShell title="Analizar texto en busca de PII" onClose={onClose} testid="ia-pii-analizar-modal">
      <div className="field">
        <label>Texto a analizar</label>
        <textarea className="textarea" rows={6}
          value={texto}
          onChange={(e) => onTexto(e.target.value)}
          placeholder="Pegue el texto a verificar (no se almacena)."
          data-testid="ia-pii-analizar-texto"
        />
      </div>
      {error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{error.message || 'Error al analizar.'}</div>
        </div>
      )}
      {resultado && (
        <div data-testid="ia-pii-analizar-resultado" style={{ marginTop: 12 }}>
          <p style={{ fontSize: 13 }}>
            Detecciones: <strong>{(resultado.detecciones || []).length}</strong>
            {' '}· severidad máxima:{' '}
            <span className={`badge ${badgeSev(resultado.severidad_max)}`}>
              {resultado.severidad_max || 'ninguna'}
            </span>
          </p>
          {(resultado.detecciones || []).length > 0 && (
            <ul data-testid="ia-pii-detecciones" style={{ paddingLeft: 16, fontSize: 12 }}>
              {resultado.detecciones.map((d, i) => (
                <li key={i}>
                  <strong>{d.tipo}</strong>: <code>{d.fragmento}</code>
                  {' '}<span className="muted">({d.severidad})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={submitting || !texto.trim()}
          onClick={onAnalizar}
          data-testid="ia-pii-analizar-submit"
        >{submitting ? 'Analizando…' : 'Analizar'}</button>
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
        style={{ width: 540, padding: 'var(--s-5)' }}>
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

function badgeSev(s) {
  if (s === 'critica') return 'danger';
  if (s === 'alta') return 'warn';
  if (s === 'media') return 'info';
  return 'neutral';
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default DeteccionPII;
