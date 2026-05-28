/**
 * ReglasAutoClasif — GD-UI-0085.
 *
 * CRUD de reglas de auto-clasificación de correo entrante.
 * Cada regla:
 *  - nombre, prioridad (orden de evaluación)
 *  - condiciones (lista AND de {campo, op, valor})
 *  - acción ({tipo: 'cola'|'descartar', cola_destino?, dependencia?})
 *  - activa (toggle)
 *  - hits (telemetría, read-only)
 *
 * Reglas evaluadas en orden de prioridad; primera que matchea aplica.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useReglasAutoClasif, useCrearReglaAutoClasif,
  useActualizarReglaAutoClasif, useEliminarReglaAutoClasif,
} from './useGdCorreo.js';

const CAMPOS = ['remitente', 'asunto', 'cuerpo', 'tiene_adjuntos'];
const OPS = ['contiene', 'igual', 'inicia_con', 'termina_con', 'regex'];

export function ReglasAutoClasif({
  session, roles = [], ...shellProps
}) {
  const puedeEditar = gdCanAny(roles, 'COR-EMAIL-005', 'RW');
  const reglas = useReglasAutoClasif(session);
  const crear = useCrearReglaAutoClasif(session);
  const actualizar = useActualizarReglaAutoClasif(session);
  const eliminar = useEliminarReglaAutoClasif(session);
  const [draft, setDraft] = useState(null);
  const [feedback, setFeedback] = useState(null);

  async function guardar() {
    setFeedback(null);
    try {
      if (draft.id) {
        await actualizar.submit(draft.id, draft);
      } else {
        await crear.submit(draft);
      }
      setFeedback({ ok: true });
      setDraft(null);
      reglas.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  async function borrar(id) {
    setFeedback(null);
    try {
      await eliminar.submit(id);
      setFeedback({ ok: true, msg: 'Regla eliminada.' });
      reglas.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Reglas auto-clasificación' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Reglas de auto-clasificación de correo</h1>
          <p className="subtitle">
            Las reglas se evalúan en orden de prioridad. La
            primera que matchea determina la acción
            (encolar / descartar). Cambios quedan en auditoría.
          </p>
        </div>
        <div className="actions">
          {puedeEditar && (
            <button type="button" className="btn btn-primary"
              onClick={() => setDraft({
                nombre: '', prioridad: 100,
                condiciones: [{ campo: 'asunto', op: 'contiene', valor: '' }],
                accion: { tipo: 'cola', cola_destino: '' },
                activa: true,
              })}
              data-testid="cor-reglas-nueva"
            >Nueva regla</button>
          )}
          <button type="button" className="btn btn-secondary"
            onClick={reglas.refresh}
            data-testid="cor-reglas-refresh"
          >Actualizar</button>
        </div>
      </div>

      {!puedeEditar && (
        <div className="alert info" role="alert"
          data-testid="cor-reglas-readonly"
        >
          <div className="body">Modo lectura — no puedes editar reglas.</div>
        </div>
      )}

      {reglas.loading && <p className="muted">Cargando…</p>}
      {reglas.error && (
        <div className="alert danger" role="alert"
          data-testid="cor-reglas-error"
        >
          <div className="body">{reglas.error.message}</div>
        </div>
      )}

      {reglas.items.length === 0 && !reglas.loading && !reglas.error && (
        <div className="empty" data-testid="cor-reglas-empty">
          <p className="muted">Sin reglas configuradas.</p>
        </div>
      )}

      {reglas.items.length > 0 && (
        <table className="data-table" data-testid="cor-reglas-tabla">
          <thead>
            <tr>
              <th className="num">Prioridad</th>
              <th>Nombre</th>
              <th>Acción</th>
              <th className="num">Hits</th>
              <th>Activa</th>
              {puedeEditar && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {reglas.items.map((r) => (
              <tr key={r.id} data-testid="cor-reglas-row">
                <td className="num">{r.prioridad}</td>
                <td>{r.nombre}</td>
                <td>
                  {r.accion?.tipo === 'descartar'
                    ? 'descartar'
                    : `→ ${r.accion?.cola_destino || r.accion?.dependencia_destino || '?'}`}
                </td>
                <td className="num">{r.hits || 0}</td>
                <td>
                  <span className={`badge ${r.activa ? 'ok' : 'muted'}`}>
                    {r.activa ? 'sí' : 'no'}
                  </span>
                </td>
                {puedeEditar && (
                  <td>
                    <button type="button" className="btn btn-sm"
                      onClick={() => setDraft({ ...r })}
                      data-testid="cor-reglas-editar"
                    >Editar</button>
                    {' '}
                    <button type="button" className="btn btn-sm btn-danger"
                      onClick={() => borrar(r.id)}
                      disabled={eliminar.loading}
                      data-testid="cor-reglas-borrar"
                    >Borrar</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {draft && (
        <div className="modal-backdrop"
          data-testid="cor-reglas-modal"
          style={{ position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.4)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
        >
          <div className="modal" style={{ background: 'white',
            padding: 'var(--s-5)', minWidth: 480, maxWidth: 640,
            maxHeight: '90vh', overflowY: 'auto', borderRadius: 8 }}
          >
            <h3 style={{ marginTop: 0 }}>
              {draft.id ? 'Editar regla' : 'Nueva regla'}
            </h3>
            <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
              Nombre
              <input type="text" value={draft.nombre}
                onChange={(e) => setDraft((d) => ({ ...d, nombre: e.target.value }))}
                style={{ width: '100%' }}
                required
                data-testid="cor-reglas-edit-nombre"
              />
            </label>
            <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
              Prioridad
              <input type="number" value={draft.prioridad}
                onChange={(e) => setDraft((d) => ({ ...d, prioridad: parseInt(e.target.value, 10) || 100 }))}
                style={{ width: 120 }}
                data-testid="cor-reglas-edit-prio"
              />
            </label>

            <strong style={{ display: 'block', marginBottom: 'var(--s-1)',
              marginTop: 'var(--s-3)' }}
            >Condiciones (AND)</strong>
            {(draft.condiciones || []).map((cond, i) => (
              <div key={i} style={{ display: 'flex', gap: 'var(--s-1)',
                marginBottom: 'var(--s-1)' }}
                data-testid="cor-reglas-cond"
              >
                <select value={cond.campo}
                  onChange={(e) => {
                    const cs = [...draft.condiciones];
                    cs[i] = { ...cs[i], campo: e.target.value };
                    setDraft((d) => ({ ...d, condiciones: cs }));
                  }}
                  data-testid="cor-reglas-cond-campo"
                >
                  {CAMPOS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <select value={cond.op}
                  onChange={(e) => {
                    const cs = [...draft.condiciones];
                    cs[i] = { ...cs[i], op: e.target.value };
                    setDraft((d) => ({ ...d, condiciones: cs }));
                  }}
                  data-testid="cor-reglas-cond-op"
                >
                  {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                <input type="text" value={cond.valor}
                  onChange={(e) => {
                    const cs = [...draft.condiciones];
                    cs[i] = { ...cs[i], valor: e.target.value };
                    setDraft((d) => ({ ...d, condiciones: cs }));
                  }}
                  style={{ flex: 1 }}
                  data-testid="cor-reglas-cond-valor"
                />
                <button type="button"
                  onClick={() => {
                    const cs = draft.condiciones.filter((_, j) => j !== i);
                    setDraft((d) => ({ ...d, condiciones: cs }));
                  }}
                  data-testid="cor-reglas-cond-rm"
                >×</button>
              </div>
            ))}
            <button type="button" className="btn btn-sm"
              onClick={() => setDraft((d) => ({
                ...d,
                condiciones: [...d.condiciones, { campo: 'asunto', op: 'contiene', valor: '' }],
              }))}
              data-testid="cor-reglas-cond-add"
            >+ Añadir condición</button>

            <strong style={{ display: 'block', marginBottom: 'var(--s-1)',
              marginTop: 'var(--s-3)' }}
            >Acción</strong>
            <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
              Tipo
              <select value={draft.accion?.tipo}
                onChange={(e) => setDraft((d) => ({
                  ...d, accion: { ...d.accion, tipo: e.target.value },
                }))}
                data-testid="cor-reglas-accion-tipo"
              >
                <option value="cola">Encolar (cola/dependencia)</option>
                <option value="descartar">Descartar</option>
              </select>
            </label>
            {draft.accion?.tipo === 'cola' && (
              <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
                Destino (cola o dependencia)
                <input type="text" value={draft.accion?.cola_destino || ''}
                  onChange={(e) => setDraft((d) => ({
                    ...d, accion: { ...d.accion, cola_destino: e.target.value },
                  }))}
                  style={{ width: '100%' }}
                  data-testid="cor-reglas-accion-dest"
                />
              </label>
            )}
            <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
              <input type="checkbox" checked={!!draft.activa}
                onChange={(e) => setDraft((d) => ({ ...d, activa: e.target.checked }))}
                data-testid="cor-reglas-edit-activa"
              />
              {' '}Activa
            </label>

            <div style={{ display: 'flex', gap: 'var(--s-2)',
              marginTop: 'var(--s-3)', justifyContent: 'flex-end' }}
            >
              <button type="button" className="btn btn-secondary"
                onClick={() => setDraft(null)}
                data-testid="cor-reglas-edit-cancelar"
              >Cancelar</button>
              <button type="button" className="btn btn-primary"
                onClick={guardar}
                disabled={crear.loading || actualizar.loading || !draft.nombre}
                data-testid="cor-reglas-edit-guardar"
              >Guardar</button>
            </div>
          </div>
        </div>
      )}

      {feedback && (
        <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
          role="status" data-testid="cor-reglas-feedback"
        >
          <div className="body">
            {feedback.ok ? (feedback.msg || 'Cambios guardados.')
              : (feedback.error?.message || 'Error.')}
          </div>
        </div>
      )}
    </GdShell>
  );
}

export default ReglasAutoClasif;
