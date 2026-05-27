/**
 * AsistenteConversacional — GD-UI-0075.
 *
 * Vista de chat. El backend aplica permisos rol-aware (no
 * filtra documentos a los que el usuario no tiene acceso).
 * Cada respuesta trae `citas` con vínculos a fuentes.
 *
 * Conversaciones persistentes en `gd.ia_conversacion`.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useAsistente, useConversacionesIa,
} from './useGdIa.js';

export function AsistenteConversacional({
  session, roles = [], onNavigate, conversacionId = null, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'IA-004', 'RW');
  const [activeId, setActiveId] = useState(conversacionId);
  const a = useAsistente(session, activeId);
  const lista = useConversacionesIa(session);
  const [input, setInput] = useState('');

  async function enviar(e) {
    e?.preventDefault?.();
    if (!input.trim() || a.loading) return;
    const msg = input.trim();
    setInput('');
    try {
      const r = await a.enviar(msg);
      if (r?.conversacion_id) {
        setActiveId(r.conversacion_id);
        lista.refresh?.();
      }
    } catch (_) { /* mostrado */ }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Asistente IA' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Asistente conversacional</h1>
          <p className="subtitle">
            Pregunta sobre el módulo en lenguaje natural. Las
            respuestas incluyen citas a documentos y respetan
            tus permisos (no verás contenido al que no tienes
            acceso).
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={() => { a.reset(); setActiveId(null); }}
            data-testid="ia-asis-nueva"
          >Nueva conversación</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="ia-asis-no-perm"
        >
          <div className="body">
            No tienes permiso para usar el asistente.
          </div>
        </div>
      )}

      {tienePermiso && (
        <div style={{ display: 'grid',
          gridTemplateColumns: '220px 1fr', gap: 'var(--s-4)' }}
        >
          <aside className="card" style={{ padding: 'var(--s-3)' }}
            data-testid="ia-asis-historial"
          >
            <h4 style={{ fontSize: 12, margin: 0,
              marginBottom: 'var(--s-2)' }}
            >Conversaciones</h4>
            {lista.loading && <p className="muted" style={{ fontSize: 12 }}>Cargando…</p>}
            {lista.error && (
              <p className="muted" style={{ fontSize: 12 }}>
                Error cargando historial.
              </p>
            )}
            {lista.items.length === 0 && !lista.loading && (
              <p className="muted" style={{ fontSize: 12 }}>
                Sin conversaciones previas.
              </p>
            )}
            <ul style={{ listStyle: 'none', padding: 0, margin: 0,
              fontSize: 12 }}
            >
              {lista.items.map((c) => (
                <li key={c.id}>
                  <button type="button"
                    onClick={() => setActiveId(c.id)}
                    className={activeId === c.id ? 'active' : ''}
                    style={{ width: '100%', textAlign: 'left',
                      padding: 'var(--s-1) var(--s-2)',
                      background: 'none', border: 0, cursor: 'pointer' }}
                    data-testid="ia-asis-conv-item"
                  >
                    <strong>{c.titulo || c.id}</strong>
                    <div className="muted">
                      {c.mensajes_count || 0} msgs ·{' '}
                      {(c.tokens_total || 0)} tokens
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <section data-testid="ia-asis-chat">
            <div className="card" style={{ padding: 'var(--s-3)',
              minHeight: 280, maxHeight: 500, overflowY: 'auto',
              marginBottom: 'var(--s-3)' }}
              data-testid="ia-asis-mensajes"
            >
              {a.mensajes.length === 0 && (
                <p className="muted">
                  Sin mensajes en esta conversación. Escribe tu
                  consulta abajo.
                </p>
              )}
              {a.mensajes.map((m, i) => (
                <div key={i}
                  className={`chat-bubble chat-bubble-${m.rol}`}
                  data-testid={`ia-asis-msg-${m.rol}`}
                  style={{
                    padding: 'var(--s-2) var(--s-3)',
                    marginBottom: 'var(--s-2)',
                    borderRadius: 8,
                    background: m.rol === 'user' ? 'var(--c-bg-soft)'
                      : 'var(--c-bg)',
                    borderLeft: m.rol === 'assistant'
                      ? '3px solid var(--c-primary)' : 'none',
                  }}
                >
                  <strong style={{ fontSize: 11, color: 'var(--c-muted)' }}>
                    {m.rol === 'user' ? 'Tú' : 'Asistente'}
                  </strong>
                  <p style={{ margin: 0, marginTop: 'var(--s-1)' }}>
                    {m.contenido}
                  </p>
                  {m.citas && m.citas.length > 0 && (
                    <details style={{ marginTop: 'var(--s-1)' }}>
                      <summary style={{ cursor: 'pointer', fontSize: 12 }}>
                        {m.citas.length} cita{m.citas.length > 1 ? 's' : ''}
                      </summary>
                      <ul style={{ fontSize: 12, marginTop: 'var(--s-1)' }}
                        data-testid="ia-asis-citas"
                      >
                        {m.citas.map((c, j) => (
                          <li key={j}>
                            <a href="#" onClick={(e) => {
                              e.preventDefault();
                              onNavigate?.(`/gd/documentos/${c.documento_id}`);
                            }}>
                              {c.titulo || c.documento_id}
                            </a>
                            {c.fragmento && (
                              <small className="muted"> — “{c.fragmento}”</small>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              ))}
              {a.loading && (
                <p className="muted" data-testid="ia-asis-loading">
                  Pensando…
                </p>
              )}
            </div>

            {a.error && (
              <div className="alert danger" role="alert"
                data-testid="ia-asis-error"
              >
                <div className="body">
                  {a.error.code === 'ia_budget_exceeded'
                    ? 'Presupuesto IA agotado.'
                    : (a.error.message || 'Error en asistente.')}
                </div>
              </div>
            )}

            <form onSubmit={enviar}
              style={{ display: 'flex', gap: 'var(--s-2)' }}
              data-testid="ia-asis-form"
            >
              <input type="text"
                value={input} onChange={(e) => setInput(e.target.value)}
                placeholder="Escribe tu pregunta…"
                disabled={a.loading}
                style={{ flex: 1 }}
                data-testid="ia-asis-input"
              />
              <button type="button" className="btn btn-primary"
                onClick={enviar}
                disabled={a.loading || !input.trim()}
                data-testid="ia-asis-enviar"
              >Enviar</button>
            </form>
          </section>
        </div>
      )}
    </GdShell>
  );
}

export default AsistenteConversacional;
