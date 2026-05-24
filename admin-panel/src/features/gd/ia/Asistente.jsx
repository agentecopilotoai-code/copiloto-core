/**
 * Asistente — GD-UI-0075. Asistente conversacional.
 *
 * Chat con el módulo: el usuario pregunta sobre PQRSD, expedientes,
 * TRD, etc. y la IA responde citando fuentes. Permisos rol-aware:
 * la IA NO ve documentos que el usuario no podría ver. IA-004.
 */
import React, { useState, useEffect, useRef } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  useEnviarMensajeAsistente,
  useConversacionesAsistente,
  useConversacionAsistente,
} from './useGdIA.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function Asistente({ session, roles = [], ...shellProps }) {
  const [convId, setConvId] = useState(null);
  const [draft, setDraft] = useState('');
  const enviar = useEnviarMensajeAsistente(session);
  const convs = useConversacionesAsistente(session);
  const conv = useConversacionAsistente(session, convId, { enabled: !!convId });
  const scrollRef = useRef(null);
  const puede = gdCanAny(roles, 'IA-004', 'R');

  const mensajes = conv.data?.mensajes || [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [mensajes.length]);

  async function handleEnviar() {
    const texto = draft.trim();
    if (!texto) return;
    setDraft('');
    try {
      const r = await enviar.submit({
        conversacion_id: convId,
        contenido: texto,
      });
      if (r?.conversacion_id && r.conversacion_id !== convId) {
        setConvId(r.conversacion_id);
        convs.refresh();
      } else {
        conv.refresh?.();
      }
    } catch { /* hook captura */ }
  }

  function handleNueva() {
    setConvId(null);
    setDraft('');
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Asistente' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Asistente del módulo</h1>
          <p className="subtitle">
            Pregunte en lenguaje natural sobre el módulo. La IA respeta
            sus permisos y cita las fuentes consultadas.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-accent"
            onClick={handleNueva}
            data-testid="ia-asis-nueva"
          >+ Nueva conversación</button>
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="ia-asis-no-perm">
          <div className="body">No tiene permisos para usar el asistente.</div>
        </div>
      )}

      {puede && (
        <div data-testid="ia-asis-layout"
          style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 'var(--s-4)' }}>
          <aside className="card" style={{ padding: 0, maxHeight: '70vh', overflow: 'auto' }}>
            <div style={{ padding: 'var(--s-3)', borderBottom: '1px solid var(--border-subtle)' }}>
              <strong style={{ fontSize: 13 }}>Conversaciones</strong>
            </div>
            {convs.loading && <p className="muted" style={{ padding: 'var(--s-3)' }}>Cargando…</p>}
            {convs.error && (
              <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
                <div className="body">{convs.error.message || 'Error.'}</div>
              </div>
            )}
            {convs.items.length === 0 && !convs.loading && (
              <p className="muted" style={{ padding: 'var(--s-3)', fontSize: 12 }}
                data-testid="ia-asis-empty-convs">
                Aún no tiene conversaciones.
              </p>
            )}
            {convs.items.map((c) => (
              <button
                key={c.id}
                type="button"
                data-testid="ia-asis-conv-row"
                onClick={() => setConvId(c.id)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: 'var(--s-3)',
                  border: 0,
                  borderBottom: '1px solid var(--border-subtle)',
                  background: convId === c.id ? 'var(--sky-50)' : 'transparent',
                  cursor: 'pointer',
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>{c.titulo || 'Sin título'}</div>
                <div className="muted" style={{ fontSize: 11 }}>
                  {fmt(c.actualizada_en || c.creada_en)}
                </div>
              </button>
            ))}
          </aside>

          <section className="card" style={{ padding: 0, display: 'flex', flexDirection: 'column', maxHeight: '70vh' }}>
            <div ref={scrollRef} data-testid="ia-asis-mensajes"
              style={{ flex: 1, overflowY: 'auto', padding: 'var(--s-4)' }}>
              {!convId && (
                <p className="muted" data-testid="ia-asis-vacio">
                  Comience escribiendo una pregunta abajo. Su consulta crea
                  una nueva conversación.
                </p>
              )}
              {conv.loading && <p className="muted">Cargando mensajes…</p>}
              {mensajes.map((m, i) => (
                <Mensaje key={m.id || i} m={m} />
              ))}
            </div>

            <form
              onSubmit={(e) => { e.preventDefault(); handleEnviar(); }}
              style={{ borderTop: '1px solid var(--border-subtle)', padding: 'var(--s-3)' }}
              data-testid="ia-asis-form"
            >
              {enviar.error && (
                <div className="alert danger" role="alert" style={{ marginBottom: 8 }}>
                  <div className="body">{enviar.error.message || 'Error al enviar.'}</div>
                </div>
              )}
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="input" style={{ flex: 1 }}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Escriba su pregunta…"
                  data-testid="ia-asis-input"
                />
                <button type="submit" className="btn btn-accent"
                  disabled={enviar.submitting || !draft.trim()}
                  data-testid="ia-asis-enviar"
                >{enviar.submitting ? 'Enviando…' : 'Enviar'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </GdShell>
  );
}

function Mensaje({ m }) {
  const esUsuario = m.rol === 'usuario' || m.role === 'user';
  return (
    <div data-testid="ia-asis-msg"
      style={{
        display: 'flex',
        justifyContent: esUsuario ? 'flex-end' : 'flex-start',
        marginBottom: 'var(--s-3)',
      }}
    >
      <div
        style={{
          maxWidth: '80%',
          background: esUsuario ? 'var(--accent-base)' : 'var(--surface-alt)',
          color: esUsuario ? 'white' : 'inherit',
          padding: 'var(--s-3)',
          borderRadius: 'var(--r-md)',
        }}
      >
        <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{m.contenido}</div>
        {(m.citas || []).length > 0 && (
          <div style={{ marginTop: 6, fontSize: 11 }}>
            <div style={{ opacity: 0.75 }}>Fuentes:</div>
            <ul data-testid="ia-asis-citas" style={{ margin: '4px 0 0', paddingLeft: 14 }}>
              {m.citas.map((c, i) => (
                <li key={i}>
                  <strong>{c.titulo || c.entidad}</strong>
                  {c.entidad_id && <> · <code style={{ fontSize: 10 }}>{c.entidad_id.slice(0, 8)}</code></>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default Asistente;
