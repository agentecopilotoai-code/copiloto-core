/**
 * BuzonCorreoEntrante — GD-UI-0079.
 *
 * Bandeja de correo institucional entrante (importado del/los canal/es
 * IMAP/POP3 configurados en COR-EMAIL-004). Filtros por canal, fecha,
 * estado (nuevo, leído, radicado, descartado). Click en fila abre
 * preview lateral con detalle del correo + adjuntos + CTAs:
 *  - "Convertir a radicado" (COR-EMAIL-002 RW) → dispara modal con
 *    selector de tipo (entrada/salida) + dependencia + clasificación.
 *  - "Descartar" (con motivo obligatorio para audit).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useCorreoEntrante, useCorreoEntranteItem,
  useConvertirARadicado, useDescartarCorreo,
} from './useGdCorreo.js';

const ESTADOS = ['nuevo', 'leido', 'radicado', 'descartado'];

export function BuzonCorreoEntrante({
  session, roles = [], onNavigate, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'COR-EMAIL-001', 'R');
  const puedeRadicar = gdCanAny(roles, 'COR-EMAIL-002', 'RW');
  const [filtros, setFiltros] = useState({});
  const [seleccionId, setSeleccionId] = useState(null);
  const [modal, setModal] = useState(null);
  const bandeja = useCorreoEntrante(session, filtros);
  const item = useCorreoEntranteItem(session, seleccionId,
    { enabled: !!seleccionId });
  const convertir = useConvertirARadicado(session);
  const descartar = useDescartarCorreo(session);
  const [feedback, setFeedback] = useState(null);

  function actualizar(k, v) {
    setFiltros((p) => ({ ...p, [k]: v || undefined }));
  }

  async function radicarSubmit() {
    setFeedback(null);
    try {
      const r = await convertir.submit(seleccionId, modal);
      setFeedback({ ok: true,
        msg: `Radicado ${r?.numero || r?.radicado_id} creado.` });
      setModal(null);
      bandeja.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  async function descartarSubmit(motivo) {
    setFeedback(null);
    try {
      await descartar.submit(seleccionId, motivo);
      setFeedback({ ok: true, msg: 'Correo descartado.' });
      setSeleccionId(null);
      bandeja.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Buzón de correo' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Buzón de correo institucional</h1>
          <p className="subtitle">
            Correos entrantes pendientes de procesar. Convierte a
            radicado para integrar al flujo o descarta con motivo
            (auditado).
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={bandeja.refresh}
            data-testid="cor-bz-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="cor-bz-no-perm"
        >
          <div className="body">No tienes acceso al buzón de correo.</div>
        </div>
      )}

      {tienePermiso && (
        <>
          {/* Filtros */}
          <div className="card" style={{ padding: 'var(--s-3)',
            marginBottom: 'var(--s-3)', display: 'flex',
            gap: 'var(--s-2)', flexWrap: 'wrap' }}
            data-testid="cor-bz-filtros"
          >
            <label style={{ fontSize: 12 }}>
              Canal{' '}
              <input type="text"
                value={filtros.canal || ''}
                onChange={(e) => actualizar('canal', e.target.value)}
                placeholder="ventanilla@…"
                data-testid="cor-bz-canal"
              />
            </label>
            <label style={{ fontSize: 12 }}>
              Estado{' '}
              <select value={filtros.estado || ''}
                onChange={(e) => actualizar('estado', e.target.value)}
                data-testid="cor-bz-estado"
              >
                <option value="">— Todos —</option>
                {ESTADOS.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 12 }}>
              Asunto{' '}
              <input type="text"
                value={filtros.asunto || ''}
                onChange={(e) => actualizar('asunto', e.target.value)}
                placeholder="texto…"
                data-testid="cor-bz-asunto"
              />
            </label>
          </div>

          {/* Layout: lista + preview */}
          <div style={{ display: 'grid',
            gridTemplateColumns: seleccionId ? '1fr 1fr' : '1fr',
            gap: 'var(--s-4)' }}
          >
            <section data-testid="cor-bz-lista">
              {bandeja.loading && <p className="muted">Cargando…</p>}
              {bandeja.error && (
                <div className="alert danger" role="alert"
                  data-testid="cor-bz-error"
                >
                  <div className="body">{bandeja.error.message}</div>
                </div>
              )}
              {bandeja.items.length === 0 && !bandeja.loading && !bandeja.error && (
                <div className="empty" data-testid="cor-bz-empty">
                  <p className="muted">Sin correos en bandeja.</p>
                </div>
              )}
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {bandeja.items.map((c) => (
                  <li key={c.id}
                    className={`card ${seleccionId === c.id ? 'active' : ''}`}
                    onClick={() => setSeleccionId(c.id)}
                    data-testid="cor-bz-item"
                    style={{ padding: 'var(--s-2) var(--s-3)',
                      marginBottom: 'var(--s-1)', cursor: 'pointer',
                      borderLeft: seleccionId === c.id
                        ? '3px solid var(--c-primary)' : '3px solid transparent' }}
                  >
                    <div style={{ display: 'flex',
                      justifyContent: 'space-between' }}
                    >
                      <strong>{c.remitente}</strong>
                      <small className="muted">{fmt(c.recibido_en)}</small>
                    </div>
                    <div>{c.asunto}</div>
                    {c.snippet && (
                      <small className="muted">{c.snippet}</small>
                    )}
                    {c.estado && (
                      <span className={`badge ${
                        c.estado === 'radicado' ? 'ok'
                          : c.estado === 'descartado' ? 'muted'
                          : c.estado === 'nuevo' ? 'warn' : ''}`}
                      >
                        {c.estado}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            {seleccionId && (
              <aside className="card"
                style={{ padding: 'var(--s-4)', position: 'sticky',
                  top: 'var(--s-4)', alignSelf: 'flex-start' }}
                data-testid="cor-bz-preview"
              >
                {item.loading && <p className="muted">Cargando preview…</p>}
                {item.error && (
                  <div className="alert danger" role="alert">
                    <div className="body">{item.error.message}</div>
                  </div>
                )}
                {item.data && (
                  <>
                    <h2 style={{ fontSize: 16, marginTop: 0 }}>
                      {item.data.asunto}
                    </h2>
                    <dl style={{ fontSize: 13 }}>
                      <dt><strong>De</strong></dt><dd>{item.data.remitente}</dd>
                      <dt><strong>Para</strong></dt>
                      <dd>{(item.data.destinatarios || []).join(', ')}</dd>
                    </dl>
                    <div style={{ marginTop: 'var(--s-3)' }}
                      data-testid="cor-bz-cuerpo"
                    >
                      {item.data.cuerpo_html ? (
                        <div dangerouslySetInnerHTML={{ __html: item.data.cuerpo_html }} />
                      ) : (
                        <pre style={{ whiteSpace: 'pre-wrap' }}>
                          {item.data.cuerpo_texto}
                        </pre>
                      )}
                    </div>
                    {(item.data.adjuntos || []).length > 0 && (
                      <div style={{ marginTop: 'var(--s-3)' }}>
                        <strong style={{ fontSize: 13 }}>Adjuntos</strong>
                        <ul data-testid="cor-bz-adjuntos">
                          {item.data.adjuntos.map((a, i) => (
                            <li key={i}>{a.nombre}{' '}
                              <small className="muted">({a.tamano} bytes)</small>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 'var(--s-2)',
                      marginTop: 'var(--s-3)' }}
                    >
                      {puedeRadicar && !item.data.ya_radicado && (
                        <button type="button" className="btn btn-primary"
                          onClick={() => setModal({
                            tipo: 'entrada', destino_dependencia: '',
                            clasificacion: '', prioridad: 'normal',
                          })}
                          data-testid="cor-bz-radicar"
                        >Convertir a radicado</button>
                      )}
                      {item.data.ya_radicado && (
                        <button type="button" className="btn btn-secondary"
                          onClick={() => onNavigate?.(`/gd/ventanilla/radicados/${item.data.radicado_id}`)}
                          data-testid="cor-bz-ir-radicado"
                        >Ver radicado #{item.data.radicado_id}</button>
                      )}
                      {puedeRadicar && !item.data.ya_radicado && (
                        <button type="button" className="btn btn-secondary"
                          onClick={() => {
                            const motivo = prompt('Motivo del descarte:');
                            if (motivo) descartarSubmit(motivo);
                          }}
                          data-testid="cor-bz-descartar"
                        >Descartar</button>
                      )}
                    </div>
                  </>
                )}
              </aside>
            )}
          </div>

          {modal && (
            <div className="modal-backdrop"
              data-testid="cor-bz-modal"
              style={{ position: 'fixed', inset: 0,
                background: 'rgba(0,0,0,0.4)', display: 'flex',
                alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
            >
              <div className="modal" style={{ background: 'white',
                padding: 'var(--s-5)', minWidth: 360, borderRadius: 8 }}
              >
                <h3 style={{ marginTop: 0 }}>Convertir a radicado</h3>
                <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
                  Tipo
                  <select value={modal.tipo}
                    onChange={(e) => setModal((m) => ({ ...m, tipo: e.target.value }))}
                    style={{ width: '100%' }}
                    data-testid="cor-bz-modal-tipo"
                  >
                    <option value="entrada">Entrada</option>
                    <option value="salida">Salida</option>
                  </select>
                </label>
                <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
                  Dependencia destino
                  <input type="text" value={modal.destino_dependencia}
                    onChange={(e) => setModal((m) => ({ ...m, destino_dependencia: e.target.value }))}
                    style={{ width: '100%' }}
                    data-testid="cor-bz-modal-dep"
                  />
                </label>
                <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
                  Clasificación
                  <input type="text" value={modal.clasificacion}
                    onChange={(e) => setModal((m) => ({ ...m, clasificacion: e.target.value }))}
                    style={{ width: '100%' }}
                    data-testid="cor-bz-modal-clasif"
                  />
                </label>
                <div style={{ display: 'flex', gap: 'var(--s-2)',
                  marginTop: 'var(--s-3)', justifyContent: 'flex-end' }}
                >
                  <button type="button" className="btn btn-secondary"
                    onClick={() => setModal(null)}
                    data-testid="cor-bz-modal-cancelar"
                  >Cancelar</button>
                  <button type="button" className="btn btn-primary"
                    onClick={radicarSubmit}
                    disabled={convertir.loading || !modal.destino_dependencia}
                    data-testid="cor-bz-modal-guardar"
                  >{convertir.loading ? 'Creando…' : 'Crear radicado'}</button>
                </div>
              </div>
            </div>
          )}

          {feedback && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" data-testid="cor-bz-feedback"
            >
              <div className="body">
                {feedback.ok ? feedback.msg : (feedback.error?.message || 'Error.')}
              </div>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default BuzonCorreoEntrante;
